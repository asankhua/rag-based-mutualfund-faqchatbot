#!/usr/bin/env python3
"""
Vercel Serverless API Entry Point for RAG-Based Mutual Fund FAQ Chatbot
"""

import os
import sys
import json
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Mutual Fund FAQ Chatbot API",
    description="RAG-based FAQ assistant for HDFC mutual funds",
    version="1.0.0",
    docs_url="/docs",
    openapi_url="/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_rag_pipeline: Optional[Any] = None

def get_rag_pipeline():
    global _rag_pipeline
    if _rag_pipeline is None:
        try:
            from phase3.phase3_rag_engine import RAGPipeline
            logger.info("Initializing RAG Pipeline...")
            _rag_pipeline = RAGPipeline()
        except Exception as e:
            logger.error(f"Failed to initialize RAG pipeline: {e}")
            raise
    return _rag_pipeline


class ChatQueryRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class ChatQueryResponse(BaseModel):
    answer: str
    sources: List[str] = []
    metadata: Dict[str, Any] = {}


class FundOverview(BaseModel):
    nav: Optional[str] = None
    returns_since_inception: Optional[str] = None
    returns_1y: Optional[str] = None
    returns_3y: Optional[str] = None
    returns_5y: Optional[str] = None
    expense_ratio: Optional[str] = None
    benchmark: Optional[str] = None
    aum: Optional[str] = None
    inception_date: Optional[str] = None
    min_lumpsum: Optional[str] = None
    min_sip: Optional[str] = None
    exit_load: Optional[str] = None
    lock_in: Optional[str] = None
    turnover: Optional[str] = None
    risk: Optional[str] = None


class Fund(BaseModel):
    scheme_id: str
    name: str
    source_url: str
    overview: FundOverview
    last_scraped_at: Optional[str] = None


class FundListResponse(BaseModel):
    funds: List[Fund]
    total: int


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str


class StatusResponse(BaseModel):
    status: str
    last_updated: Optional[str] = None
    total_funds: int
    data_freshness: str
    timestamp: str


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


@app.options("/{full_path:path}")
async def preflight_handler(full_path: str):
    """Handle CORS preflight requests."""
    return {"status": "ok"}


@app.get("/status", response_model=StatusResponse)
async def get_status():
    try:
        data_dir = PROJECT_ROOT / "data" / "phase1"
        last_updated = None
        total_funds = 0
        data_freshness = "unknown"
        
        if data_dir.exists():
            scrape_times = []
            for json_file in data_dir.glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        fund_data = json.load(f)
                    total_funds += 1
                    scraped_at = fund_data.get("last_scraped_at")
                    if scraped_at:
                        scrape_times.append(datetime.fromisoformat(scraped_at.replace("Z", "+00:00")))
                except:
                    pass
            
            if scrape_times:
                last_updated_dt = max(scrape_times)
                last_updated = last_updated_dt.isoformat()
                now = datetime.utcnow()
                age = now - last_updated_dt.replace(tzinfo=None)
                data_freshness = "fresh" if age.total_seconds() < 48 * 3600 else "stale"
        
        return StatusResponse(
            status="healthy",
            last_updated=last_updated,
            total_funds=total_funds,
            data_freshness=data_freshness,
            timestamp=datetime.utcnow().isoformat() + "Z"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat/query", response_model=ChatQueryResponse)
async def chat_query(request: ChatQueryRequest):
    try:
        pipeline = get_rag_pipeline()
        response = pipeline.query(request.message)
        return ChatQueryResponse(
            answer=response.answer,
            sources=response.sources,
            metadata=response.metadata
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/funds", response_model=FundListResponse)
async def list_funds():
    try:
        data_dir = PROJECT_ROOT / "data" / "phase1"
        funds = []
        
        if not data_dir.exists():
            raise HTTPException(status_code=404, detail="Fund data not found")
        
        for json_file in sorted(data_dir.glob("*.json")):
            with open(json_file, "r", encoding="utf-8") as f:
                fund_data = json.load(f)
                funds.append(Fund(
                    scheme_id=fund_data["scheme_id"],
                    name=fund_data["name"],
                    source_url=fund_data["source_url"],
                    overview=FundOverview(**fund_data.get("overview", {})),
                    last_scraped_at=fund_data.get("last_scraped_at")
                ))
        
        return FundListResponse(funds=funds, total=len(funds))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/funds/{scheme_id}", response_model=Fund)
async def get_fund(scheme_id: str):
    try:
        json_file = PROJECT_ROOT / "data" / "phase1" / f"{scheme_id}.json"
        
        if not json_file.exists():
            raise HTTPException(status_code=404, detail=f"Fund not found: {scheme_id}")
        
        with open(json_file, "r", encoding="utf-8") as f:
            fund_data = json.load(f)
        
        return Fund(
            scheme_id=fund_data["scheme_id"],
            name=fund_data["name"],
            source_url=fund_data["source_url"],
            overview=FundOverview(**fund_data.get("overview", {})),
            last_scraped_at=fund_data.get("last_scraped_at")
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Vercel handler
from mangum import Mangum
handler = Mangum(app, lifespan="off")
