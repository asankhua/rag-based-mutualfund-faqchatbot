#!/usr/bin/env python3
"""
Lightweight FastAPI backend for Render deployment.
Uses pre-computed embeddings to avoid loading heavy ML models.
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
    
    with open(data_dir / "chunks.json", "r") as f:
        chunks = json.load(f)
    
    with open(data_dir / "metadata.json", "r") as f:
        metadata = json.load(f)
    
    embeddings = np.load(data_dir / "embeddings.npy")
    
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
    data_dir = PROJECT_ROOT / "data" / "phase1"
    total_funds = len(list(data_dir.glob("*.json"))) if data_dir.exists() else 0
    
    return {
        "status": "healthy",
        "total_funds": total_funds,
        "data_freshness": "fresh",
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
        
        # Extract sources from chunks
        sources = []
        for chunk in relevant_chunks:
            if "Source:" in chunk:
                source = chunk.split("Source:")[-1].strip()
                if source and source not in sources:
                    sources.append(source)
        
        return ChatQueryResponse(answer=answer, sources=sources)
        
    except Exception as e:
        print(f"Error in chat_query: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
