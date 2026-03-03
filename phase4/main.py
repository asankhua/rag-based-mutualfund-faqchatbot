#!/usr/bin/env python3
"""
Phase 4 - Backend & API Layer for RAG-Based Mutual Fund FAQ Chatbot

FastAPI application providing:
- Chat/RAG API for user queries
- Fund metadata APIs
- Admin ingestion endpoints
"""

import os
import sys
import json
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, HTTPException, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

from phase3.phase3_rag_engine import RAGPipeline, RAGResponse
from phase2.phase2_indexer import Phase2Indexer
from phase1.phase1_scraper import scrape_fund_data, ALLOWLISTED_URLS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Mutual Fund FAQ Chatbot API",
    description="RAG-based FAQ assistant for HDFC mutual funds",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize RAG pipeline (lazy loading)
_rag_pipeline: Optional[RAGPipeline] = None

def get_rag_pipeline() -> RAGPipeline:
    """Get or initialize RAG pipeline."""
    global _rag_pipeline
    if _rag_pipeline is None:
        logger.info("Initializing RAG Pipeline...")
        _rag_pipeline = RAGPipeline()
    return _rag_pipeline


# ============================================================================
# Pydantic Models
# ============================================================================

class ChatQueryRequest(BaseModel):
    """Request model for chat query."""
    message: str = Field(..., description="User query message", min_length=1)
    session_id: Optional[str] = Field(None, description="Session ID for logging")
    user_id: Optional[str] = Field(None, description="User ID for logging (not used for personalization)")


class ChatQueryResponse(BaseModel):
    """Response model for chat query."""
    answer: str = Field(..., description="Assistant's answer")
    sources: List[str] = Field(default_factory=list, description="List of source URLs")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class FundOverview(BaseModel):
    """Fund overview model."""
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
    """Fund model for list endpoint."""
    scheme_id: str
    name: str
    source_url: str
    overview: FundOverview
    last_scraped_at: Optional[str] = None


class FundListResponse(BaseModel):
    """Response model for fund list."""
    funds: List[Fund]
    total: int


class IngestResponse(BaseModel):
    """Response model for ingestion."""
    status: str
    message: str
    scheme_id: Optional[str] = None
    timestamp: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    timestamp: str
    version: str


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint - API info."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + "Z",
        version="1.0.0"
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat() + "Z",
        version="1.0.0"
    )


# ----------------------------------------------------------------------------
# Chat/RAG Endpoints
# ----------------------------------------------------------------------------

@app.post("/chat/query", response_model=ChatQueryResponse)
async def chat_query(request: ChatQueryRequest):
    """
    Process a user query through the RAG pipeline.
    
    - Classifies query intent
    - Retrieves relevant chunks
    - Generates answer using Groq
    - Returns answer with sources
    """
    try:
        logger.info(f"Received query: {request.message}")
        
        # Log query metadata (without sensitive info)
        logger.info(f"Query metadata - session_id: {request.session_id}, user_id: {request.user_id}")
        
        # Get RAG pipeline and process query
        pipeline = get_rag_pipeline()
        response = pipeline.query(request.message)
        
        # Log response metadata
        logger.info(f"Response metadata - intent: {response.metadata.get('intent')}, "
                   f"is_refusal: {response.metadata.get('is_refusal')}, "
                   f"chunks_retrieved: {response.metadata.get('chunks_retrieved', 0)}")
        
        return ChatQueryResponse(
            answer=response.answer,
            sources=response.sources,
            metadata=response.metadata
        )
        
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing query: {str(e)}"
        )


# ----------------------------------------------------------------------------
# Fund Metadata Endpoints
# ----------------------------------------------------------------------------

@app.get("/funds", response_model=FundListResponse)
async def list_funds():
    """
    List all supported mutual funds with their metadata.
    """
    try:
        data_dir = Path(__file__).parent.parent / "data" / "phase1"
        funds = []
        
        if not data_dir.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Fund data not found. Run ingestion first."
            )
        
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
        logger.error(f"Error listing funds: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing funds: {str(e)}"
        )


@app.get("/funds/{scheme_id}", response_model=Fund)
async def get_fund(scheme_id: str):
    """
    Get detailed information about a specific fund.
    """
    try:
        json_file = Path(__file__).parent.parent / "data" / "phase1" / f"{scheme_id}.json"
        
        if not json_file.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Fund not found: {scheme_id}"
            )
        
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
        logger.error(f"Error getting fund {scheme_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting fund: {str(e)}"
        )


# ----------------------------------------------------------------------------
# Admin/Ingestion Endpoints
# ----------------------------------------------------------------------------

def run_ingestion(scheme_id: Optional[str] = None):
    """Background task for running ingestion."""
    try:
        if scheme_id:
            logger.info(f"Starting ingestion for scheme: {scheme_id}")
            # Find URL for scheme
            url = None
            for u in ALLOWLISTED_URLS:
                if scheme_id in u:
                    url = u
                    break
            
            if not url:
                logger.error(f"URL not found for scheme: {scheme_id}")
                return
            
            # Scrape and save
            fund_data = scrape_fund_data(url)
            from phase1.phase1_scraper import save_fund_data
            save_fund_data(fund_data)
            logger.info(f"Ingestion complete for {scheme_id}")
            
            # Re-run Phase 2 indexing for this fund
            indexer = Phase2Indexer()
            indexer.index_fund(scheme_id)
            indexer.vector_store.save()
            logger.info(f"Re-indexing complete for {scheme_id}")
            
        else:
            logger.info("Starting full ingestion for all funds")
            from phase1.phase1_scraper import scrape_all_funds
            scrape_all_funds()
            logger.info("Phase 1 scraping complete")
            
            # Run Phase 2 indexing
            indexer = Phase2Indexer()
            indexer.index_all_funds()
            logger.info("Phase 2 indexing complete")
            
    except Exception as e:
        logger.error(f"Ingestion error: {str(e)}")


@app.post("/admin/ingest", response_model=IngestResponse)
async def ingest_all(background_tasks: BackgroundTasks):
    """
    Trigger ingestion for all funds (runs in background).
    """
    background_tasks.add_task(run_ingestion)
    
    return IngestResponse(
        status="started",
        message="Ingestion started for all funds. This may take several minutes.",
        timestamp=datetime.utcnow().isoformat() + "Z"
    )


@app.post("/admin/ingest/{scheme_id}", response_model=IngestResponse)
async def ingest_single(scheme_id: str, background_tasks: BackgroundTasks):
    """
    Trigger ingestion for a single fund (runs in background).
    """
    # Validate scheme_id
    valid_scheme = any(scheme_id in url for url in ALLOWLISTED_URLS)
    if not valid_scheme:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid scheme_id: {scheme_id}"
        )
    
    background_tasks.add_task(run_ingestion, scheme_id)
    
    return IngestResponse(
        status="started",
        message=f"Ingestion started for {scheme_id}",
        scheme_id=scheme_id,
        timestamp=datetime.utcnow().isoformat() + "Z"
    )


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("Starting Mutual Fund FAQ Chatbot API")
    print("=" * 60)
    print("\nAPI Documentation: http://localhost:8000/docs")
    print("Health Check: http://localhost:8000/health")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 60)
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
