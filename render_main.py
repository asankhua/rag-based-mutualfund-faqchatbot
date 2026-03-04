#!/usr/bin/env python3
"""
Lightweight FastAPI backend for Render deployment.
Uses pre-computed embeddings to avoid loading heavy ML models.
Includes automatic daily scheduler for data updates.
"""

import os
import sys
import json
import numpy as np
import asyncio
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from groq import Groq
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Global variable to track last scheduler run
LAST_SCHEDULER_RUN = None

app = FastAPI(
    title="Mutual Fund FAQ Chatbot API",
    description="RAG-based FAQ assistant for HDFC mutual funds",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load Groq client
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# Load pre-computed data
def load_data():
    """Load pre-computed chunks and embeddings."""
    data_dir = PROJECT_ROOT / "data" / "phase2"
    
    with open(data_dir / "chunks.json", "r") as f:
        chunk_objects = json.load(f)
    
    with open(data_dir / "metadata.json", "r") as f:
        metadata = json.load(f)
    
    embeddings = np.load(data_dir / "embeddings.npy")
    
    # Extract text from chunk objects
    chunks = [chunk["text"] for chunk in chunk_objects if "text" in chunk]
    
    return chunks, embeddings, metadata

# Load data on startup
try:
    CHUNKS, EMBEDDINGS, METADATA = load_data()
    print(f"Loaded {len(CHUNKS)} chunks")
except Exception as e:
    print(f"Error loading data: {e}")
    CHUNKS, EMBEDDINGS, METADATA = [], None, {}


class ChatQueryRequest(BaseModel):
    message: str = Field(..., min_length=1)


class ChatQueryResponse(BaseModel):
    answer: str
    sources: List[str] = []


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str


def cosine_similarity(a, b):
    """Calculate cosine similarity between two vectors."""
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def retrieve_chunks(query: str, top_k: int = 5):
    """Simple keyword-based retrieval without embeddings model."""
    query_lower = query.lower()
    scores = []
    
    for i, chunk in enumerate(CHUNKS):
        score = 0
        chunk_lower = chunk.lower()
        
        # Simple keyword matching
        query_words = set(query_lower.split())
        chunk_words = set(chunk_lower.split())
        common_words = query_words & chunk_words
        
        score = len(common_words) / max(len(query_words), 1)
        
        # Boost exact phrase matches
        if query_lower in chunk_lower:
            score += 0.5
            
        scores.append((i, score))
    
    # Sort by score and return top_k
    scores.sort(key=lambda x: x[1], reverse=True)
    top_indices = [idx for idx, score in scores[:top_k] if score > 0]
    
    return [CHUNKS[i] for i in top_indices]


@app.get("/", response_model=HealthResponse)
async def root():
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + "Z",
        version="1.0.0"
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + "Z",
        version="1.0.0"
    )


@app.get("/status")
async def get_status():
    global LAST_SCHEDULER_RUN
    
    data_dir = PROJECT_ROOT / "data" / "phase1"
    total_funds = 0
    last_data_update = None
    
    if data_dir.exists():
        scrape_times = []
        for json_file in data_dir.glob("*.json"):
            try:
                with open(json_file, "r") as f:
                    fund_data = json.load(f)
                total_funds += 1
                scraped_at = fund_data.get("last_scraped_at")
                if scraped_at:
                    scrape_times.append(datetime.fromisoformat(scraped_at.replace("Z", "+00:00")))
            except:
                pass
        
        if scrape_times:
            last_data_update = max(scrape_times).isoformat()
    
    # Use scheduler run time as the last_updated if available
    display_last_updated = LAST_SCHEDULER_RUN or last_data_update
    
    return {
        "status": "healthy",
        "total_funds": total_funds,
        "last_updated": display_last_updated,
        "last_scheduler_run": LAST_SCHEDULER_RUN,
        "last_data_update": last_data_update,
        "data_freshness": "fresh" if display_last_updated else "unknown",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@app.get("/funds")
async def list_funds():
    data_dir = PROJECT_ROOT / "data" / "phase1"
    funds = []
    
    if data_dir.exists():
        for json_file in sorted(data_dir.glob("*.json")):
            with open(json_file, "r") as f:
                fund_data = json.load(f)
                funds.append({
                    "scheme_id": fund_data["scheme_id"],
                    "name": fund_data["name"],
                    "source_url": fund_data["source_url"],
                    "overview": fund_data.get("overview", {}),
                    "last_scraped_at": fund_data.get("last_scraped_at")
                })
    
    return {"funds": funds, "total": len(funds)}


@app.get("/funds/{scheme_id}")
async def get_fund(scheme_id: str):
    json_file = PROJECT_ROOT / "data" / "phase1" / f"{scheme_id}.json"
    
    if not json_file.exists():
        raise HTTPException(status_code=404, detail=f"Fund not found: {scheme_id}")
    
    with open(json_file, "r") as f:
        return json.load(f)


@app.post("/chat/query")
async def chat_query(request: ChatQueryRequest):
    try:
        # Retrieve relevant chunks
        relevant_chunks = retrieve_chunks(request.message)
        
        if not relevant_chunks:
            return ChatQueryResponse(
                answer="I don't have specific information about that in my knowledge base. Please ask about one of the available HDFC mutual funds.",
                sources=[]
            )
        
        # Build context
        context = "\n\n".join(relevant_chunks)
        
        # Create prompt
        prompt = f"""You are a factual FAQ assistant for HDFC mutual funds. Use ONLY the provided context to answer the question. Do not provide investment advice. If the information is not in the context, say you don't have that information.

Context:
{context}

Question: {request.message}

Answer:"""
        
        # Call Groq API
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": "You are a helpful FAQ assistant that only provides factual information about mutual funds."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=500
        )
        
        answer = response.choices[0].message.content
        
        # Extract sources from chunks - get only the URL
        import re
        sources = []
        for chunk in relevant_chunks:
            # Extract URL from Source: line
            match = re.search(r'Source:\s*(https?://[^\s\n]+)', chunk)
            if match:
                url = match.group(1)
                if url and url not in sources:
                    sources.append(url)
        
        return ChatQueryResponse(answer=answer, sources=sources)
        
    except Exception as e:
        print(f"Error in chat_query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def run_scheduler_task():
    """Background task to run the full pipeline."""
    global LAST_SCHEDULER_RUN, CHUNKS
    
    try:
        print(f"[{datetime.now()}] Starting scheduled data update...")
        
        # Phase 1: Scrape data
        print("Phase 1: Scraping fund data...")
        from phase1.phase1_scraper import scrape_all_funds
        scrape_all_funds()
        
        # Phase 2: Index data
        print("Phase 2: Indexing fund data...")
        from phase2.phase2_indexer import Phase2Indexer
        indexer = Phase2Indexer()
        indexer.index_all_funds()
        indexer.vector_store.save()
        
        # Reload data in memory
        print("Reloading data in memory...")
        CHUNKS, _, _ = load_data()
        
        LAST_SCHEDULER_RUN = datetime.utcnow().isoformat() + "Z"
        print(f"[{datetime.now()}] Scheduled update completed successfully!")
        
    except Exception as e:
        print(f"[{datetime.now()}] Scheduler error: {e}")


def start_scheduler():
    """Start the background scheduler."""
    scheduler = BackgroundScheduler()
    
    # Run daily at 9:00 AM UTC
    trigger = CronTrigger(hour=9, minute=0)
    
    scheduler.add_job(
        run_scheduler_task,
        trigger=trigger,
        id='daily_data_update',
        name='Daily Fund Data Update',
        replace_existing=True
    )
    
    scheduler.start()
    print(f"[{datetime.now()}] Scheduler started. Next run at 9:00 AM UTC.")
    
    # Run once on startup to ensure data is fresh
    threading.Thread(target=run_scheduler_task, daemon=True).start()


# Start scheduler when module loads
start_scheduler()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
