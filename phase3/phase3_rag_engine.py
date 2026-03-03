#!/usr/bin/env python3
"""
Phase 3 RAG Answering Engine with Groq for Mutual Fund FAQ Chatbot

This module implements the RAG pipeline with:
- Query classification/intent detection
- Vector retrieval from Phase 2 embeddings
- Groq LLM integration for answer generation
- Strict guardrails for no advice, no PII, mandatory sources
"""

import os
import re
import json
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np
from groq import Groq
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Import Phase 2 components
import sys
sys.path.append(str(Path(__file__).parent.parent))
from phase2.phase2_indexer import SimpleVectorStore, EmbeddingGenerator


class QueryIntent(Enum):
    """Query intent categories."""
    FUND_FACT = "fund_fact"
    CONCEPT_EXPLANATION = "concept_explanation"
    OPINION_ADVISORY = "opinion_advisory"
    PERSONAL_ACCOUNT = "personal_account"
    OUT_OF_DOMAIN = "out_of_domain"


@dataclass
class ClassifiedQuery:
    """Represents a classified user query."""
    original_query: str
    intent: QueryIntent
    confidence: float
    mentioned_schemes: List[str] = field(default_factory=list)
    is_refusal: bool = False
    refusal_reason: Optional[str] = None


@dataclass
class RAGResponse:
    """Represents the final RAG response."""
    answer: str
    sources: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)


class QueryClassifier:
    """Classifies user queries into intent categories."""
    
    # Scheme name mappings for detection
    SCHEME_ALIASES = {
        "hdfc-flexi-cap-fund-direct-plan-growth-option-3184": [
            "hdfc flexi cap", "flexi cap fund", "flexi cap"
        ],
        "hdfc-small-cap-fund-direct-growth-option-3580": [
            "hdfc small cap", "small cap fund", "small cap"
        ],
        "hdfc-nifty-midcap-150-index-fund-direct-growth-1043788": [
            "hdfc nifty midcap 150", "nifty midcap 150", "midcap 150 index"
        ],
        "hdfc-mid-cap-fund-direct-plan-growth-option-3097": [
            "hdfc mid cap", "mid cap fund", "mid cap"
        ],
        "hdfc-banking-financial-services-fund-direct-growth-1006661": [
            "hdfc banking", "banking fund", "financial services fund", "banking & financial"
        ],
        "hdfc-defence-fund-direct-growth-1043873": [
            "hdfc defence", "defence fund", "defense fund"
        ],
        "hdfc-nifty-private-bank-etf-1042349": [
            "hdfc nifty private bank", "private bank etf", "nifty private bank"
        ],
        "hdfc-focused-fund-direct-plan-growth-option-2795": [
            "hdfc focused", "focused fund"
        ],
    }
    
    # Advisory/opinion keywords
    ADVISORY_KEYWORDS = [
        "should i buy", "should i sell", "should i hold", "should i invest",
        "is it good", "is it bad", "best fund", "better fund", "recommend",
        "suggestion", "advice", "which fund to", "which one should", "which fund is",
        "worth investing", "good investment", "bad investment",
        "will it go up", "will it go down", "future performance",
        "predict", "forecast", "expected returns", "best for me"
    ]
    
    # Personal/account keywords
    PERSONAL_KEYWORDS = [
        "my portfolio", "my account", "my sip", "my investment",
        "my kyc", "my pan", "login", "password", "otp",
        "my returns", "my units", "my holdings", "my balance",
        "check my", "update my", "change my", "my profile"
    ]
    
    # Concept/explanation keywords (generic, not fund-specific)
    CONCEPT_KEYWORDS = [
        "what is exit load", "what is expense ratio", "what is nav",
        "what is aum", "what is benchmark", "what is turnover",
        "explain exit load", "explain expense ratio", "explain nav",
        "meaning of exit load", "meaning of expense ratio", "meaning of nav",
        "definition of exit load", "definition of expense ratio"
    ]
    
    # Fund-fact keywords (specific to fund data)
    FUND_FACT_KEYWORDS = [
        "nav of", "nav for", "expense ratio of", "expense ratio for",
        "aum of", "aum for", "returns of", "returns for",
        "benchmark of", "benchmark for", "risk of", "risk for",
        "minimum investment", "exit load of", "exit load for",
        "lock-in", "turnover of", "inception date"
    ]
    
    def classify(self, query: str) -> ClassifiedQuery:
        """Classify a user query."""
        query_lower = query.lower()
        
        # Detect mentioned schemes
        mentioned_schemes = self._detect_schemes(query_lower)
        
        # Check for personal/account queries (highest priority)
        if self._contains_keywords(query_lower, self.PERSONAL_KEYWORDS):
            return ClassifiedQuery(
                original_query=query,
                intent=QueryIntent.PERSONAL_ACCOUNT,
                confidence=0.9,
                mentioned_schemes=mentioned_schemes,
                is_refusal=True,
                refusal_reason="Personal/account-specific query detected"
            )
        
        # Check for advisory/opinion queries
        if self._contains_keywords(query_lower, self.ADVISORY_KEYWORDS):
            return ClassifiedQuery(
                original_query=query,
                intent=QueryIntent.OPINION_ADVISORY,
                confidence=0.85,
                mentioned_schemes=mentioned_schemes,
                is_refusal=True,
                refusal_reason="Advisory/opinion query detected"
            )
        
        # Check for concept/explanation queries (generic, no scheme mentioned)
        if not mentioned_schemes and self._contains_keywords(query_lower, self.CONCEPT_KEYWORDS):
            return ClassifiedQuery(
                original_query=query,
                intent=QueryIntent.CONCEPT_EXPLANATION,
                confidence=0.8,
                mentioned_schemes=mentioned_schemes
            )
        
        # Check for fund-fact queries (schemes mentioned OR fund-fact keywords)
        if mentioned_schemes or self._contains_keywords(query_lower, self.FUND_FACT_KEYWORDS):
            return ClassifiedQuery(
                original_query=query,
                intent=QueryIntent.FUND_FACT,
                confidence=0.8,
                mentioned_schemes=mentioned_schemes
            )
        
        # Default to out-of-domain
        return ClassifiedQuery(
            original_query=query,
            intent=QueryIntent.OUT_OF_DOMAIN,
            confidence=0.5,
            mentioned_schemes=mentioned_schemes
        )
    
    def _detect_schemes(self, query: str) -> List[str]:
        """Detect mentioned schemes in the query."""
        mentioned = []
        for scheme_id, aliases in self.SCHEME_ALIASES.items():
            for alias in aliases:
                if alias in query:
                    mentioned.append(scheme_id)
                    break
        return mentioned
    
    def _contains_keywords(self, query: str, keywords: List[str]) -> bool:
        """Check if query contains any of the keywords."""
        return any(keyword in query for keyword in keywords)


class RetrievalEngine:
    """Retrieves relevant chunks from the vector store."""
    
    def __init__(self, vector_store: SimpleVectorStore, embedding_generator: EmbeddingGenerator):
        self.vector_store = vector_store
        self.embedding_generator = embedding_generator
        self.similarity_threshold = 0.3  # Minimum similarity score
    
    def retrieve(
        self, 
        query: str, 
        scheme_ids: Optional[List[str]] = None,
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant chunks for a query."""
        # Generate query embedding
        query_embedding = self.embedding_generator.generate_embedding(query)
        
        # Search vector store
        results = self.vector_store.search(query_embedding, top_k=top_k * 2)  # Get more for filtering
        
        # Filter by scheme if specified
        if scheme_ids:
            results = [
                r for r in results 
                if r.get("scheme_id") in scheme_ids
            ]
        
        # Filter by similarity threshold
        results = [
            r for r in results 
            if r.get("similarity", 0) >= self.similarity_threshold
        ]
        
        # Return top_k after filtering
        return results[:top_k]


class GroqLLMClient:
    """Client for Groq LLM API."""
    
    # System prompt for the RAG assistant
    SYSTEM_PROMPT = """You are a facts-only mutual fund FAQ assistant for HDFC mutual funds on INDMoney.

CRITICAL RULES:
1. Use ONLY the provided context chunks to answer. Do NOT use any external knowledge.
2. If information is missing in the context, clearly state "I don't have this information in my current dataset."
3. NEVER provide investment advice, buy/sell/hold recommendations, or portfolio guidance.
4. NEVER answer personal/account-specific questions (portfolio, KYC, login, etc.).
5. ALWAYS include a "Sources" section with URLs from the context.
6. Be concise and factual. Do not make predictions about future performance.
7. IMPORTANT: Deduplicate source URLs - list each unique URL only once in the Sources section.

For opinionated/advisory questions, politely refuse and explain that you are a facts-only assistant.

Response format:
- Provide a clear, factual answer based on the context
- End with a "Sources" section listing unique URLs (no duplicates)
"""

    # Refusal response for advisory queries
    ADVISORY_REFUSAL = """I'm a facts-only assistant and cannot provide opinions, personalized recommendations, or buy/sell advice.

I can share objective details like NAV, past returns, expense ratio, and risk level. Deciding if a fund is right for you depends on your goals and risk profile.

For personalized guidance, please consult a SEBI-registered financial advisor or use official INDMoney tools.

Sources:
- https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId=13 (SEBI Investor Education)
"""

    # Refusal response for personal/account queries
    PERSONAL_REFUSAL = """I'm unable to help with personal or account-specific queries such as portfolio details, KYC status, or account information.

For assistance with your personal account, please:
- Log in to your INDMoney account
- Contact INDMoney support through the app
- Or visit https://www.indmoney.com/support

Sources:
- https://www.indmoney.com/support
"""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Groq client."""
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("Groq API key required. Set GROQ_API_KEY environment variable.")
        
        self.client = Groq(api_key=self.api_key)
        self.model = "llama-3.1-8b-instant"  # Default model, can be changed
    
    def generate_response(
        self, 
        query: str, 
        context_chunks: List[Dict[str, Any]],
        is_refusal: bool = False,
        refusal_type: Optional[str] = None
    ) -> str:
        """Generate response using Groq LLM."""
        
        # Handle refusal cases
        if is_refusal:
            if refusal_type == "advisory":
                return self.ADVISORY_REFUSAL
            elif refusal_type == "personal":
                return self.PERSONAL_REFUSAL
        
        # If no context chunks, return information not available
        if not context_chunks:
            return "I don't have this information in my current dataset.\n\nSources:\n- No relevant sources found"
        
        # Build context from chunks
        context = self._build_context(context_chunks)
        
        # Build messages
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer based on the context above."}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,  # Low temperature for factual responses
                max_tokens=1024,
            )
            
            answer = response.choices[0].message.content
            
            # Ensure sources are included
            if "Sources:" not in answer:
                sources = self._extract_sources(context_chunks)
                answer += f"\n\nSources:\n{sources}"
            else:
                # Deduplicate sources in the answer
                answer = self._deduplicate_sources_in_answer(answer)
            
            return answer
            
        except Exception as e:
            return f"I apologize, but I encountered an error generating the response. Please try again.\n\nError: {str(e)}"
    
    def _build_context(self, chunks: List[Dict[str, Any]]) -> str:
        """Build context string from chunks."""
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            text = chunk.get("text", "")
            source = chunk.get("source_url", "")
            context_parts.append(f"[Document {i}]\n{text}\nSource: {source}\n")
        
        return "\n---\n".join(context_parts)
    
    def _extract_sources(self, chunks: List[Dict[str, Any]]) -> str:
        """Extract unique sources from chunks."""
        sources = set()
        for chunk in chunks:
            source = chunk.get("source_url", "")
            if source:
                sources.add(f"- {source}")
        
        # Add educational link if no sources
        if not sources:
            sources.add("- https://www.indmoney.com/mutual-funds")
        
        return "\n".join(sorted(sources))
    
    def _deduplicate_sources_in_answer(self, answer: str) -> str:
        """Deduplicate sources in the LLM-generated answer."""
        # Split answer into content and sources
        if "Sources:" not in answer:
            return answer
        
        parts = answer.split("Sources:", 1)
        content = parts[0].strip()
        sources_section = parts[1].strip()
        
        # Extract unique sources
        seen = set()
        unique_sources = []
        
        for line in sources_section.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Normalize the URL (remove bullet points, etc.)
            url = line.lstrip("- ").strip()
            if url and url not in seen:
                seen.add(url)
                unique_sources.append(f"- {url}")
        
        # Rebuild answer with deduplicated sources
        if unique_sources:
            return f"{content}\n\nSources:\n" + "\n".join(unique_sources)
        else:
            return content


class RAGPipeline:
    """Main RAG pipeline orchestrator."""
    
    def __init__(
        self,
        groq_api_key: Optional[str] = None,
        vector_store_dir: Optional[Path] = None
    ):
        """Initialize the RAG pipeline."""
        if vector_store_dir is None:
            # Get the project root directory
            project_root = Path(__file__).parent.parent
            vector_store_dir = project_root / "data" / "phase2"
        """Initialize the RAG pipeline."""
        print("Initializing RAG Pipeline...")
        
        # Initialize components
        self.classifier = QueryClassifier()
        self.embedding_generator = EmbeddingGenerator()
        self.vector_store = SimpleVectorStore(vector_store_dir)
        
        # Load vector store
        if not self.vector_store.load():
            raise FileNotFoundError(f"Vector store not found at {vector_store_dir}")
        
        self.retrieval_engine = RetrievalEngine(self.vector_store, self.embedding_generator)
        self.llm_client = GroqLLMClient(groq_api_key)
        
        print("RAG Pipeline initialized successfully!")
    
    def query(self, user_query: str) -> RAGResponse:
        """Process a user query through the RAG pipeline."""
        
        # Step 1: Classify the query
        classified = self.classifier.classify(user_query)
        
        # Step 2: Handle refusal cases
        if classified.is_refusal:
            refusal_type = "advisory" if classified.intent == QueryIntent.OPINION_ADVISORY else "personal"
            answer = self.llm_client.generate_response(
                user_query, 
                [], 
                is_refusal=True, 
                refusal_type=refusal_type
            )
            
            return RAGResponse(
                answer=answer,
                sources=["https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId=13"],
                metadata={
                    "intent": classified.intent.value,
                    "is_refusal": True,
                    "refusal_reason": classified.refusal_reason
                }
            )
        
        # Step 3: Retrieve relevant chunks
        retrieved_chunks = self.retrieval_engine.retrieve(
            query=user_query,
            scheme_ids=classified.mentioned_schemes if classified.mentioned_schemes else None,
            top_k=5
        )
        
        # Step 4: Generate response
        answer = self.llm_client.generate_response(
            user_query, 
            retrieved_chunks
        )
        
        # Step 5: Extract sources
        sources = self._extract_unique_sources(retrieved_chunks)
        
        return RAGResponse(
            answer=answer,
            sources=sources,
            metadata={
                "intent": classified.intent.value,
                "mentioned_schemes": classified.mentioned_schemes,
                "chunks_retrieved": len(retrieved_chunks),
                "is_refusal": False
            }
        )
    
    def _extract_unique_sources(self, chunks: List[Dict[str, Any]]) -> List[str]:
        """Extract unique source URLs from chunks."""
        sources = set()
        for chunk in chunks:
            source = chunk.get("source_url", "")
            if source:
                sources.add(source)
        return list(sources)


def main():
    """Main entry point for testing Phase 3."""
    print("=" * 60)
    print("Phase 3: RAG Answering Engine with Groq")
    print("=" * 60)
    
    # Check for API key
    if not os.getenv("GROQ_API_KEY"):
        print("\nWARNING: GROQ_API_KEY environment variable not set!")
        print("Please set it with: export GROQ_API_KEY='your-api-key'")
        print("\nFor testing, you can get a free API key from https://console.groq.com")
        return
    
    # Initialize pipeline
    pipeline = RAGPipeline()
    
    # Test queries
    test_queries = [
        "What is the NAV of HDFC Flexi Cap Fund?",
        "What is the expense ratio of HDFC Small Cap Fund?",
        "Should I buy HDFC Defence Fund?",
        "What is my SIP amount?",
        "What is exit load?",
        "Which fund is best for me?",
    ]
    
    print("\n" + "=" * 60)
    print("Testing RAG Pipeline")
    print("=" * 60)
    
    for query in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print("=" * 60)
        
        response = pipeline.query(query)
        
        print(f"\nIntent: {response.metadata.get('intent')}")
        print(f"Refusal: {response.metadata.get('is_refusal', False)}")
        print(f"\nAnswer:\n{response.answer}")
        print(f"\nSources: {response.sources}")


if __name__ == "__main__":
    main()
