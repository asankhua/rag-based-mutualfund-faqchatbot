#!/usr/bin/env python3
"""
Phase 2 Indexer for RAG-Based Mutual Fund FAQ Chatbot

This module transforms canonical fund data into semantic text chunks,
generates embeddings, and stores them in a vector database for retrieval.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


# Configuration
DATA_DIR = Path("data/phase1")
OUTPUT_DIR = Path("data/phase2")
CHROMA_DIR = Path("data/chroma")

# Embedding model - using a lightweight but effective model
# This can be swapped for other models as needed
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


@dataclass
class TextChunk:
    """Represents a text chunk with metadata for embedding."""
    id: str
    text: str
    scheme_id: str
    scheme_name: str
    source_url: str
    chunk_type: str  # overview, returns, fees, min_investment, risk
    tags: List[str] = field(default_factory=list)
    scraped_at: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk to dictionary format."""
        return {
            "id": self.id,
            "text": self.text,
            "scheme_id": self.scheme_id,
            "scheme_name": self.scheme_name,
            "source_url": self.source_url,
            "chunk_type": self.chunk_type,
            "tags": self.tags,
            "scraped_at": self.scraped_at,
        }


class FundDataLoader:
    """Loads fund data from Phase 1 JSON files."""
    
    @staticmethod
    def load_all_funds(data_dir: Path = DATA_DIR) -> List[Dict[str, Any]]:
        """Load all fund data from JSON files."""
        funds = []
        if not data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {data_dir}")
        
        for json_file in data_dir.glob("*.json"):
            with open(json_file, "r", encoding="utf-8") as f:
                fund_data = json.load(f)
                funds.append(fund_data)
        
        return funds
    
    @staticmethod
    def load_fund(scheme_id: str, data_dir: Path = DATA_DIR) -> Optional[Dict[str, Any]]:
        """Load a specific fund by scheme_id."""
        json_file = data_dir / f"{scheme_id}.json"
        if not json_file.exists():
            return None
        
        with open(json_file, "r", encoding="utf-8") as f:
            return json.load(f)


class ChunkGenerator:
    """Generates semantic text chunks from fund data."""
    
    CHUNK_TYPES = {
        "overview": ["overview", "fund-info"],
        "returns": ["returns", "performance"],
        "fees": ["fees", "expenses"],
        "min_investment": ["min-investment", "investment"],
        "risk": ["risk", "risk-profile"],
    }
    
    def generate_chunks(self, fund_data: Dict[str, Any]) -> List[TextChunk]:
        """Generate all chunks for a fund."""
        chunks = []
        
        scheme_id = fund_data["scheme_id"]
        scheme_name = fund_data["name"]
        source_url = fund_data["source_url"]
        scraped_at = fund_data.get("last_scraped_at")
        overview = fund_data.get("overview", {})
        
        # Generate overview chunk
        chunks.append(self._generate_overview_chunk(
            scheme_id, scheme_name, source_url, overview, scraped_at
        ))
        
        # Generate returns chunk
        chunks.append(self._generate_returns_chunk(
            scheme_id, scheme_name, source_url, overview, scraped_at
        ))
        
        # Generate fees chunk
        chunks.append(self._generate_fees_chunk(
            scheme_id, scheme_name, source_url, overview, scraped_at
        ))
        
        # Generate min investment chunk
        chunks.append(self._generate_min_investment_chunk(
            scheme_id, scheme_name, source_url, overview, scraped_at
        ))
        
        # Generate risk chunk
        chunks.append(self._generate_risk_chunk(
            scheme_id, scheme_name, source_url, overview, scraped_at
        ))
        
        return chunks
    
    def _generate_overview_chunk(
        self, scheme_id: str, scheme_name: str, source_url: str,
        overview: Dict[str, Any], scraped_at: Optional[str]
    ) -> TextChunk:
        """Generate the overview chunk."""
        nav = overview.get("nav", "N/A")
        aum = overview.get("aum", "N/A")
        inception_date = overview.get("inception_date", "N/A")
        benchmark = overview.get("benchmark", "N/A")
        
        text = f"""{scheme_name} – Overview
Source: {source_url}

As on {self._extract_date_from_nav(nav)}, the NAV of {scheme_name} is {self._extract_nav_value(nav)}. 
The scheme's benchmark is {benchmark}. 
The Assets Under Management (AUM) are {aum}. 
The fund was launched on {inception_date}.

This is an open-ended equity scheme investing across large cap, mid cap, and small cap stocks."""
        
        return TextChunk(
            id=str(uuid.uuid4()),
            text=text,
            scheme_id=scheme_id,
            scheme_name=scheme_name,
            source_url=source_url,
            chunk_type="overview",
            tags=self.CHUNK_TYPES["overview"],
            scraped_at=scraped_at,
        )
    
    def _generate_returns_chunk(
        self, scheme_id: str, scheme_name: str, source_url: str,
        overview: Dict[str, Any], scraped_at: Optional[str]
    ) -> TextChunk:
        """Generate the returns & performance chunk."""
        returns_since_inception = overview.get("returns_since_inception", "N/A")
        returns_1y = overview.get("returns_1y")
        returns_3y = overview.get("returns_3y")
        returns_5y = overview.get("returns_5y")
        
        text = f"""{scheme_name} – Returns & Performance
Source: {source_url}

{scheme_name} has delivered the following returns:
- Since Inception: {returns_since_inception}"""
        
        if returns_1y:
            text += f"\n- 1 Year: {returns_1y}"
        if returns_3y:
            text += f"\n- 3 Years: {returns_3y}"
        if returns_5y:
            text += f"\n- 5 Years: {returns_5y}"
        
        text += """

Past performance is not indicative of future returns."""
        
        return TextChunk(
            id=str(uuid.uuid4()),
            text=text,
            scheme_id=scheme_id,
            scheme_name=scheme_name,
            source_url=source_url,
            chunk_type="returns",
            tags=self.CHUNK_TYPES["returns"],
            scraped_at=scraped_at,
        )
    
    def _generate_fees_chunk(
        self, scheme_id: str, scheme_name: str, source_url: str,
        overview: Dict[str, Any], scraped_at: Optional[str]
    ) -> TextChunk:
        """Generate the fees & expenses chunk."""
        expense_ratio = overview.get("expense_ratio", "N/A")
        exit_load = overview.get("exit_load", "N/A")
        
        text = f"""{scheme_name} – Fees & Expenses
Source: {source_url}

The expense ratio for {scheme_name} is {expense_ratio}.
The exit load is {exit_load}.

The expense ratio represents the annual fee that the fund charges for managing the investments. 
The exit load is a fee charged when investors redeem their units within a specified period."""
        
        return TextChunk(
            id=str(uuid.uuid4()),
            text=text,
            scheme_id=scheme_id,
            scheme_name=scheme_name,
            source_url=source_url,
            chunk_type="fees",
            tags=self.CHUNK_TYPES["fees"],
            scraped_at=scraped_at,
        )
    
    def _generate_min_investment_chunk(
        self, scheme_id: str, scheme_name: str, source_url: str,
        overview: Dict[str, Any], scraped_at: Optional[str]
    ) -> TextChunk:
        """Generate the minimum investment & exit load chunk."""
        min_lumpsum = overview.get("min_lumpsum", "N/A")
        min_sip = overview.get("min_sip", "N/A")
        exit_load = overview.get("exit_load", "N/A")
        lock_in = overview.get("lock_in", "N/A")
        
        text = f"""{scheme_name} – Minimum Investment & Exit Load
Source: {source_url}

Minimum Investment:
- Lumpsum: {min_lumpsum}
- SIP: {min_sip}

Exit Load: {exit_load}
Lock-in Period: {lock_in}

The minimum investment amount is the smallest amount an investor can invest in the fund. 
SIP (Systematic Investment Plan) allows regular periodic investments. 
Exit load applies if units are redeemed before the specified holding period."""
        
        return TextChunk(
            id=str(uuid.uuid4()),
            text=text,
            scheme_id=scheme_id,
            scheme_name=scheme_name,
            source_url=source_url,
            chunk_type="min_investment",
            tags=self.CHUNK_TYPES["min_investment"],
            scraped_at=scraped_at,
        )
    
    def _generate_risk_chunk(
        self, scheme_id: str, scheme_name: str, source_url: str,
        overview: Dict[str, Any], scraped_at: Optional[str]
    ) -> TextChunk:
        """Generate the risk profile chunk."""
        risk = overview.get("risk", "N/A")
        turnover = overview.get("turnover", "N/A")
        benchmark = overview.get("benchmark", "N/A")
        
        text = f"""{scheme_name} – Risk Profile
Source: {source_url}

SEBI Risk Label: {risk}
Portfolio Turnover: {turnover}
Benchmark: {benchmark}

The SEBI risk label indicates the level of risk associated with the fund. 
"Very High Risk" indicates that the fund may experience significant price fluctuations. 
Portfolio turnover indicates how frequently assets within the fund are bought and sold.

This is an equity fund and is subject to market risks. Please read all scheme-related documents carefully before investing."""
        
        return TextChunk(
            id=str(uuid.uuid4()),
            text=text,
            scheme_id=scheme_id,
            scheme_name=scheme_name,
            source_url=source_url,
            chunk_type="risk",
            tags=self.CHUNK_TYPES["risk"],
            scraped_at=scraped_at,
        )
    
    @staticmethod
    def _extract_nav_value(nav_str: str) -> str:
        """Extract NAV value from NAV string."""
        if not nav_str or nav_str == "N/A":
            return "N/A"
        # Extract value before "(as on"
        parts = nav_str.split("(as on")
        return parts[0].strip() if parts else nav_str
    
    @staticmethod
    def _extract_date_from_nav(nav_str: str) -> str:
        """Extract date from NAV string."""
        if not nav_str or nav_str == "N/A":
            return "N/A"
        # Extract date between "as on" and ")"
        if "as on" in nav_str:
            parts = nav_str.split("as on")
            if len(parts) > 1:
                date_part = parts[1].strip()
                return date_part.rstrip(")").strip()
        return "N/A"


class EmbeddingGenerator:
    """Generates embeddings using sentence-transformers."""
    
    def __init__(self, model_name: str = EMBEDDING_MODEL):
        """Initialize the embedding model."""
        print(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
        print(f"Model loaded. Embedding dimension: {self.dimension}")
    
    def generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for a single text."""
        embedding = self.model.encode(text, convert_to_numpy=True)
        return embedding
    
    def generate_embeddings(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings for multiple texts."""
        embeddings = self.model.encode(texts, convert_to_numpy=True)
        return embeddings


class SimpleVectorStore:
    """Simple vector store using JSON files (for local development)."""
    
    def __init__(self, output_dir: Path = OUTPUT_DIR):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.chunks_file = output_dir / "chunks.json"
        self.embeddings_file = output_dir / "embeddings.npy"
        self.metadata_file = output_dir / "metadata.json"
        
        self.chunks: List[Dict[str, Any]] = []
        self.embeddings: List[np.ndarray] = []
        self.metadata: Dict[str, Any] = {
            "created_at": datetime.utcnow().isoformat() + "Z",
            "embedding_model": EMBEDDING_MODEL,
            "total_chunks": 0,
        }
    
    def add_chunks(self, chunks: List[TextChunk], embeddings: np.ndarray):
        """Add chunks and their embeddings to the store."""
        for i, chunk in enumerate(chunks):
            chunk_dict = chunk.to_dict()
            chunk_dict["embedding_index"] = len(self.chunks) + i
            self.chunks.append(chunk_dict)
        
        self.embeddings.append(embeddings)
        self.metadata["total_chunks"] = len(self.chunks)
    
    def save(self):
        """Save the vector store to disk."""
        # Save chunks as JSON
        with open(self.chunks_file, "w", encoding="utf-8") as f:
            json.dump(self.chunks, f, indent=2, ensure_ascii=False)
        
        # Save embeddings as numpy array
        if self.embeddings:
            all_embeddings = np.vstack(self.embeddings)
            np.save(self.embeddings_file, all_embeddings)
        
        # Save metadata
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2)
        
        print(f"Vector store saved to {self.output_dir}")
        print(f"Total chunks: {self.metadata['total_chunks']}")
    
    def load(self) -> bool:
        """Load the vector store from disk."""
        if not self.chunks_file.exists():
            return False
        
        with open(self.chunks_file, "r", encoding="utf-8") as f:
            self.chunks = json.load(f)
        
        if self.embeddings_file.exists():
            self.embeddings = [np.load(self.embeddings_file)]
        
        if self.metadata_file.exists():
            with open(self.metadata_file, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)
        
        return True
    
    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar chunks using cosine similarity."""
        if not self.embeddings:
            return []
        
        all_embeddings = np.vstack(self.embeddings)
        
        # Normalize embeddings for cosine similarity
        query_norm = query_embedding / np.linalg.norm(query_embedding)
        embeddings_norm = all_embeddings / np.linalg.norm(all_embeddings, axis=1, keepdims=True)
        
        # Compute cosine similarities
        similarities = np.dot(embeddings_norm, query_norm)
        
        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            chunk = self.chunks[idx].copy()
            chunk["similarity"] = float(similarities[idx])
            results.append(chunk)
        
        return results


class Phase2Indexer:
    """Main class for Phase 2 indexing pipeline."""
    
    def __init__(self):
        self.data_loader = FundDataLoader()
        self.chunk_generator = ChunkGenerator()
        self.embedding_generator = EmbeddingGenerator()
        self.vector_store = SimpleVectorStore()
    
    def index_all_funds(self) -> int:
        """Index all funds from Phase 1 data."""
        print("Loading fund data from Phase 1...")
        funds = self.data_loader.load_all_funds()
        print(f"Loaded {len(funds)} funds")
        
        total_chunks = 0
        
        for fund_data in funds:
            scheme_name = fund_data["name"]
            print(f"\nProcessing: {scheme_name}")
            
            # Generate chunks
            chunks = self.chunk_generator.generate_chunks(fund_data)
            print(f"  Generated {len(chunks)} chunks")
            
            # Generate embeddings
            texts = [chunk.text for chunk in chunks]
            embeddings = self.embedding_generator.generate_embeddings(texts)
            print(f"  Generated embeddings: {embeddings.shape}")
            
            # Add to vector store
            self.vector_store.add_chunks(chunks, embeddings)
            total_chunks += len(chunks)
        
        # Save vector store
        self.vector_store.save()
        
        return total_chunks
    
    def index_fund(self, scheme_id: str) -> int:
        """Index a specific fund."""
        fund_data = self.data_loader.load_fund(scheme_id)
        if not fund_data:
            raise ValueError(f"Fund not found: {scheme_id}")
        
        print(f"Processing: {fund_data['name']}")
        
        # Generate chunks
        chunks = self.chunk_generator.generate_chunks(fund_data)
        
        # Generate embeddings
        texts = [chunk.text for chunk in chunks]
        embeddings = self.embedding_generator.generate_embeddings(texts)
        
        # Add to vector store
        self.vector_store.add_chunks(chunks, embeddings)
        
        return len(chunks)
    
    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Search the vector store with a query."""
        # Generate query embedding
        query_embedding = self.embedding_generator.generate_embedding(query)
        
        # Search vector store
        results = self.vector_store.search(query_embedding, top_k)
        
        return results


def main():
    """Main entry point for Phase 2 indexing."""
    print("=" * 60)
    print("Phase 2: Knowledge Modeling, Chunking & Embeddings")
    print("=" * 60)
    
    indexer = Phase2Indexer()
    
    # Index all funds
    total_chunks = indexer.index_all_funds()
    
    print("\n" + "=" * 60)
    print(f"Indexing complete! Total chunks created: {total_chunks}")
    print("=" * 60)
    
    # Test search
    print("\nTesting search functionality...")
    test_queries = [
        "What is the NAV of HDFC Flexi Cap Fund?",
        "What is the expense ratio?",
        "Tell me about the risk profile",
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        results = indexer.search(query, top_k=2)
        for i, result in enumerate(results, 1):
            print(f"  Result {i}: {result['scheme_name']} ({result['chunk_type']}) - Score: {result['similarity']:.4f}")


if __name__ == "__main__":
    main()
