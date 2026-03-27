#!/usr/bin/env python3
"""
Lightweight FastAPI backend for Render deployment.
Uses pre-computed embeddings to avoid loading heavy ML models.
Data is updated via GitHub Actions scheduler.
"""

import os
import sys
import json
import numpy as np
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
    
    print(f"Loading data from: {data_dir}")
    print(f"Data dir exists: {data_dir.exists()}")
    
    if not data_dir.exists():
        raise FileNotFoundError(f"Data directory not found: {data_dir}")
    
    chunks_file = data_dir / "chunks.json"
    metadata_file = data_dir / "metadata.json"
    embeddings_file = data_dir / "embeddings.npy"
    
    print(f"chunks.json exists: {chunks_file.exists()}")
    print(f"metadata.json exists: {metadata_file.exists()}")
    print(f"embeddings.npy exists: {embeddings_file.exists()}")
    
    with open(chunks_file, "r") as f:
        chunk_objects = json.load(f)
    
    with open(metadata_file, "r") as f:
        metadata = json.load(f)
    
    embeddings = np.load(embeddings_file)
    
    # Extract text from chunk objects and keep full objects for scheme filtering
    chunk_objects = [c for c in chunk_objects if "text" in c and "scheme_name" in c]
    chunks = [chunk["text"] for chunk in chunk_objects]
    
    print(f"Loaded {len(chunks)} chunks, embeddings shape: {embeddings.shape}")
    
    return chunks, chunk_objects, embeddings, metadata

# Mapping of query phrases to scheme_name (order matters: more specific first)
SCHEME_NAME_PATTERNS = [
    ("hdfc small cap fund", "HDFC Small Cap Fund"),
    ("hdfc small cap", "HDFC Small Cap Fund"),
    ("hdfc mid cap fund", "HDFC Mid Cap Fund"),
    ("hdfc mid cap", "HDFC Mid Cap Fund"),
    ("hdfc flexi cap fund", "HDFC Flexi Cap Fund"),
    ("hdfc flexi cap", "HDFC Flexi Cap Fund"),
    ("hdfc focused fund", "HDFC Focused Fund"),
    ("hdfc focused", "HDFC Focused Fund"),
    ("hdfc banking & financial services fund", "HDFC Banking & Financial Services Fund"),
    ("hdfc banking and financial services", "HDFC Banking & Financial Services Fund"),
    ("hdfc banking fund", "HDFC Banking & Financial Services Fund"),
    ("hdfc defence fund", "HDFC Defence Fund"),
    ("hdfc defence", "HDFC Defence Fund"),
    ("hdfc nifty private bank etf", "HDFC Nifty Private Bank ETF Fund"),
    ("hdfc nifty private bank", "HDFC Nifty Private Bank ETF Fund"),
    ("hdfc nifty midcap 150 index fund", "HDFC NIFTY Midcap 150 Index Fund"),
    ("hdfc nifty midcap 150", "HDFC NIFTY Midcap 150 Index Fund"),
    ("nifty midcap 150 index", "HDFC NIFTY Midcap 150 Index Fund"),
]


def _detect_scheme_name(query: str) -> Optional[str]:
    """Detect which fund/scheme the user is asking about from the query."""
    query_lower = query.lower().strip()
    for phrase, scheme_name in SCHEME_NAME_PATTERNS:
        if phrase in query_lower:
            return scheme_name
    return None


# Load data on startup
try:
    CHUNKS, CHUNK_OBJECTS, EMBEDDINGS, METADATA = load_data()
    print(f"SUCCESS: Loaded {len(CHUNKS)} chunks")
except Exception as e:
    print(f"ERROR loading data: {e}")
    import traceback
    traceback.print_exc()
    CHUNKS, CHUNK_OBJECTS, EMBEDDINGS, METADATA = [], [], None, {}


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
    """Retrieve chunks using scheme-name detection and keyword matching."""
    print(f"Retrieving chunks for query: '{query}'")
    print(f"Total chunks available: {len(CHUNKS)}")
    
    if len(CHUNKS) == 0 or not CHUNK_OBJECTS:
        print("WARNING: No chunks loaded!")
        return []
    
    # Step 1: Detect if user is asking about a specific fund
    detected_scheme = _detect_scheme_name(query)
    if detected_scheme:
        # Filter to only chunks for that fund - ensures correct fund is always returned
        matching = [c["text"] for c in CHUNK_OBJECTS if c.get("scheme_name") == detected_scheme]
        if matching:
            result = matching[:top_k]
            print(f"Matched scheme '{detected_scheme}': returning {len(result)} chunks")
            return result
    
    # Step 2: Fallback to keyword-based matching for generic queries
    query_lower = query.lower()
    scores = []
    
    for i, chunk in enumerate(CHUNKS):
        score = 0
        chunk_lower = chunk.lower()
        
        # Keyword matching
        query_words = set(query_lower.split())
        chunk_words = set(chunk_lower.split())
        common_words = query_words & chunk_words
        score = len(common_words) / max(len(query_words), 1)
        
        # Boost for fund name matches (avoid generic "hdfc" - it matches all funds)
        fund_phrases = ["flexi cap", "small cap", "mid cap", "banking", "defence", 
                        "nifty midcap", "private bank", "focused"]
        for phrase in fund_phrases:
            if phrase in query_lower and phrase in chunk_lower:
                score += 0.8  # Stronger boost to differentiate funds
        
        # Boost exact phrase matches
        if query_lower in chunk_lower:
            score += 1.0
            
        scores.append((i, score))
    
    # Sort by score and return top_k
    scores.sort(key=lambda x: x[1], reverse=True)
    print(f"Top scores: {scores[:3]}")
    
    top_indices = [idx for idx, _ in scores[:top_k]]
    result = [CHUNKS[i] for i in top_indices]
    print(f"Returning {len(result)} chunks")
    return result


@app.get("/", response_model=HealthResponse)
async def root():
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + "Z",
        version="1.0.0"
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    # Check if data is loaded
    data_loaded = len(CHUNKS) > 0 and EMBEDDINGS is not None
    status = "healthy" if data_loaded else "unhealthy"
    
    return HealthResponse(
        status=status,
        timestamp=datetime.utcnow().isoformat() + "Z",
        version="1.0.0"
    )


def get_scheduler_metadata():
    """Read scheduler metadata from file."""
    metadata_file = PROJECT_ROOT / "data" / "scheduler_metadata.json"
    if metadata_file.exists():
        try:
            with open(metadata_file, "r") as f:
                return json.load(f)
        except:
            pass
    return {}


@app.get("/status")
async def get_status():
    data_dir = PROJECT_ROOT / "data" / "phase1"
    phase2_dir = PROJECT_ROOT / "data" / "phase2"
    total_funds = 0
    last_data_update = None
    
    # Check data directories
    phase1_exists = data_dir.exists()
    phase2_exists = phase2_dir.exists()
    chunks_loaded = len(CHUNKS)
    
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
    
    # Get scheduler metadata
    scheduler_meta = get_scheduler_metadata()
    last_scheduler_run = scheduler_meta.get("last_run")
    
    # Use scheduler run time as the last_updated if available
    display_last_updated = last_scheduler_run or last_data_update
    
    return {
        "status": "healthy" if chunks_loaded > 0 else "unhealthy",
        "total_funds": total_funds,
        "chunks_loaded": chunks_loaded,
        "phase1_exists": phase1_exists,
        "phase2_exists": phase2_exists,
        "project_root": str(PROJECT_ROOT),
        "last_updated": display_last_updated,
        "last_scheduler_run": last_scheduler_run,
        "last_data_update": last_data_update,
        "data_freshness": "fresh" if display_last_updated else "unknown",
        "scheduler_enabled": True,
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
        # Check if chunks are loaded
        if len(CHUNKS) == 0:
            return ChatQueryResponse(
                answer="Error: No data loaded. Please check the backend configuration.",
                sources=[]
            )
        
        # Retrieve relevant chunks
        relevant_chunks = retrieve_chunks(request.message)
        
        # If no relevant chunks found, use first 3 chunks as fallback
        if not relevant_chunks:
            relevant_chunks = CHUNKS[:3]
        
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
