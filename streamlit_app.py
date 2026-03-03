#!/usr/bin/env python3
"""
Streamlit Deployment - RAG-Based Mutual Fund FAQ Chatbot

This is a single-file Streamlit application that combines:
- Phase 1: Data from scraped JSON files
- Phase 2: Pre-computed embeddings and chunks
- Phase 3: RAG pipeline with Groq
- Phase 4/5: Web UI via Streamlit
"""

import os
import sys
import json
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

import streamlit as st
from groq import Groq
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Page configuration
st.set_page_config(
    page_title="Mutual Fund FAQ Chatbot",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# Types and Data Classes
# ============================================================================

class QueryIntent(Enum):
    FUND_FACT = "fund_fact"
    CONCEPT_EXPLANATION = "concept_explanation"
    OPINION_ADVISORY = "opinion_advisory"
    PERSONAL_ACCOUNT = "personal_account"
    OUT_OF_DOMAIN = "out_of_domain"

@dataclass
class ClassifiedQuery:
    original_query: str
    intent: QueryIntent
    confidence: float
    mentioned_schemes: List[str] = field(default_factory=list)
    is_refusal: bool = False
    refusal_reason: Optional[str] = None

@dataclass
class RAGResponse:
    answer: str
    sources: List[str]
    metadata: Dict[str, Any] = field(default_factory=dict)

# ============================================================================
# Configuration
# ============================================================================

DATA_DIR = Path("data/phase1")
CHUNKS_FILE = Path("data/phase2/chunks.json")
EMBEDDINGS_FILE = Path("data/phase2/embeddings.npy")

# Scheme aliases for detection
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

# Keyword patterns
ADVISORY_KEYWORDS = [
    "should i buy", "should i sell", "should i hold", "should i invest",
    "is it good", "is it bad", "best fund", "better fund", "recommend",
    "suggestion", "advice", "which fund to", "which one should", "which fund is",
    "worth investing", "good investment", "bad investment",
    "will it go up", "will it go down", "future performance",
    "predict", "forecast", "expected returns", "best for me"
]

PERSONAL_KEYWORDS = [
    "my portfolio", "my account", "my sip", "my investment",
    "my kyc", "my pan", "login", "password", "otp",
    "my returns", "my units", "my holdings", "my balance",
    "check my", "update my", "change my", "my profile"
]

CONCEPT_KEYWORDS = [
    "what is exit load", "what is expense ratio", "what is nav",
    "what is aum", "what is benchmark", "what is turnover",
    "explain exit load", "explain expense ratio", "explain nav",
]

FUND_FACT_KEYWORDS = [
    "nav of", "nav for", "expense ratio of", "expense ratio for",
    "aum of", "aum for", "returns of", "returns for",
    "benchmark of", "benchmark for", "risk of", "risk for",
    "minimum investment", "exit load of", "exit load for",
    "lock-in", "turnover of", "inception date"
]

# ============================================================================
# Query Classifier
# ============================================================================

class QueryClassifier:
    def classify(self, query: str) -> ClassifiedQuery:
        query_lower = query.lower()
        mentioned_schemes = self._detect_schemes(query_lower)
        
        # Check for personal/account queries
        if self._contains_keywords(query_lower, PERSONAL_KEYWORDS):
            return ClassifiedQuery(
                original_query=query,
                intent=QueryIntent.PERSONAL_ACCOUNT,
                confidence=0.9,
                mentioned_schemes=mentioned_schemes,
                is_refusal=True,
                refusal_reason="Personal/account-specific query detected"
            )
        
        # Check for advisory/opinion queries
        if self._contains_keywords(query_lower, ADVISORY_KEYWORDS):
            return ClassifiedQuery(
                original_query=query,
                intent=QueryIntent.OPINION_ADVISORY,
                confidence=0.85,
                mentioned_schemes=mentioned_schemes,
                is_refusal=True,
                refusal_reason="Advisory/opinion query detected"
            )
        
        # Check for concept/explanation queries
        if not mentioned_schemes and self._contains_keywords(query_lower, CONCEPT_KEYWORDS):
            return ClassifiedQuery(
                original_query=query,
                intent=QueryIntent.CONCEPT_EXPLANATION,
                confidence=0.8,
                mentioned_schemes=mentioned_schemes
            )
        
        # Check for fund-fact queries
        if mentioned_schemes or self._contains_keywords(query_lower, FUND_FACT_KEYWORDS):
            return ClassifiedQuery(
                original_query=query,
                intent=QueryIntent.FUND_FACT,
                confidence=0.8,
                mentioned_schemes=mentioned_schemes
            )
        
        return ClassifiedQuery(
            original_query=query,
            intent=QueryIntent.OUT_OF_DOMAIN,
            confidence=0.5,
            mentioned_schemes=mentioned_schemes
        )
    
    def _detect_schemes(self, query: str) -> List[str]:
        mentioned = []
        for scheme_id, aliases in SCHEME_ALIASES.items():
            for alias in aliases:
                if alias in query:
                    mentioned.append(scheme_id)
                    break
        return mentioned
    
    def _contains_keywords(self, query: str, keywords: List[str]) -> bool:
        return any(keyword in query for keyword in keywords)

# ============================================================================
# Vector Store
# ============================================================================

@st.cache_resource
def get_embedding_model():
    """Load and cache the embedding model."""
    return SentenceTransformer("all-MiniLM-L6-v2")

@st.cache_resource
def get_vector_store():
    """Load and cache the vector store data."""
    if not CHUNKS_FILE.exists() or not EMBEDDINGS_FILE.exists():
        return None, None
    
    with open(CHUNKS_FILE, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    
    embeddings = np.load(EMBEDDINGS_FILE)
    return chunks, embeddings

def search_vectors(query: str, chunks: List[Dict], embeddings: np.ndarray, model, top_k: int = 5, scheme_ids: Optional[List[str]] = None):
    """Search for relevant chunks using cosine similarity."""
    query_embedding = model.encode(query, convert_to_numpy=True)
    
    # Normalize
    query_norm = query_embedding / np.linalg.norm(query_embedding)
    embeddings_norm = embeddings / np.linalg.norm(embeddings, axis=1, keepdims=True)
    
    # Compute similarities
    similarities = np.dot(embeddings_norm, query_norm)
    
    # Get top indices
    top_indices = np.argsort(similarities)[::-1]
    
    results = []
    for idx in top_indices:
        chunk = chunks[idx]
        similarity = float(similarities[idx])
        
        if similarity < 0.3:  # Threshold
            continue
        
        if scheme_ids and chunk.get("scheme_id") not in scheme_ids:
            continue
        
        results.append({**chunk, "similarity": similarity})
        
        if len(results) >= top_k:
            break
    
    return results

# ============================================================================
# Groq LLM Client
# ============================================================================

SYSTEM_PROMPT = """You are a facts-only mutual fund FAQ assistant for HDFC mutual funds on INDMoney.

CRITICAL RULES:
1. Use ONLY the provided context chunks to answer. Do NOT use any external knowledge.
2. If information is missing in the context, clearly state "I don't have this information in my current dataset."
3. NEVER provide investment advice, buy/sell/hold recommendations, or portfolio guidance.
4. NEVER answer personal/account-specific questions (portfolio, KYC, login, etc.).
5. ALWAYS include a "Sources" section with URLs from the context.
6. Be concise and factual. Do not make predictions about future performance.

For opinionated/advisory questions, politely refuse and explain that you are a facts-only assistant.

Response format:
- Provide a clear, factual answer based on the context
- End with a "Sources" section listing the URLs
"""

ADVISORY_REFUSAL = """I'm a facts-only assistant and cannot provide opinions, personalized recommendations, or buy/sell advice.

I can share objective details like NAV, past returns, expense ratio, and risk level. Deciding if a fund is right for you depends on your goals and risk profile.

For personalized guidance, please consult a SEBI-registered financial advisor or use official INDMoney tools.

Sources:
- https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId=13 (SEBI Investor Education)
"""

PERSONAL_REFUSAL = """I'm unable to help with personal or account-specific queries such as portfolio details, KYC status, or account information.

For assistance with your personal account, please:
- Log in to your INDMoney account
- Contact INDMoney support through the app
- Or visit https://www.indmoney.com/support

Sources:
- https://www.indmoney.com/support
"""

def generate_response(query: str, chunks: List[Dict], is_refusal: bool = False, refusal_type: Optional[str] = None) -> str:
    """Generate response using Groq LLM."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "Error: GROQ_API_KEY not configured."
    
    if is_refusal:
        if refusal_type == "advisory":
            return ADVISORY_REFUSAL
        elif refusal_type == "personal":
            return PERSONAL_REFUSAL
    
    if not chunks:
        return "I don't have this information in my current dataset.\n\nSources:\n- No relevant sources found"
    
    # Build context
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        text = chunk.get("text", "")
        source = chunk.get("source_url", "")
        context_parts.append(f"[Document {i}]\n{text}\nSource: {source}\n")
    
    context = "\n---\n".join(context_parts)
    
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer based on the context above."}
            ],
            temperature=0.3,
            max_tokens=1024,
        )
        
        answer = response.choices[0].message.content
        
        # Ensure sources are included
        if "Sources:" not in answer:
            sources = set()
            for chunk in chunks:
                source = chunk.get("source_url", "")
                if source:
                    sources.add(f"- {source}")
            if sources:
                answer += f"\n\nSources:\n" + "\n".join(sorted(sources))
        
        return answer
        
    except Exception as e:
        return f"Error generating response: {str(e)}"

# ============================================================================
# RAG Pipeline
# ============================================================================

def rag_query(query: str, chunks: List[Dict], embeddings: np.ndarray, model) -> RAGResponse:
    """Process a query through the RAG pipeline."""
    classifier = QueryClassifier()
    classified = classifier.classify(query)
    
    # Handle refusal cases
    if classified.is_refusal:
        refusal_type = "advisory" if classified.intent == QueryIntent.OPINION_ADVISORY else "personal"
        answer = generate_response(query, [], is_refusal=True, refusal_type=refusal_type)
        return RAGResponse(
            answer=answer,
            sources=["https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doRecognisedFpi=yes&intmId=13"],
            metadata={"intent": classified.intent.value, "is_refusal": True}
        )
    
    # Retrieve relevant chunks
    retrieved_chunks = search_vectors(
        query, chunks, embeddings, model,
        top_k=5,
        scheme_ids=classified.mentioned_schemes if classified.mentioned_schemes else None
    )
    
    # Generate response
    answer = generate_response(query, retrieved_chunks)
    
    # Extract sources
    sources = list(set(chunk.get("source_url", "") for chunk in retrieved_chunks if chunk.get("source_url")))
    
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

# ============================================================================
# Load Funds Data
# ============================================================================

@st.cache_data
def load_funds():
    """Load fund data from JSON files."""
    funds = []
    if not DATA_DIR.exists():
        return funds
    
    for json_file in sorted(DATA_DIR.glob("*.json")):
        with open(json_file, "r", encoding="utf-8") as f:
            funds.append(json.load(f))
    
    return funds

# ============================================================================
# Streamlit UI
# ============================================================================

def main():
    # Custom CSS
    st.markdown("""
    <style>
    .main-header {
        font-size: 2rem;
        font-weight: bold;
        color: #6366f1;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #6b7280;
        margin-bottom: 2rem;
    }
    .disclaimer-box {
        background-color: #1e1b4b;
        border-left: 4px solid #6366f1;
        padding: 1rem;
        margin-bottom: 1rem;
        border-radius: 0.5rem;
        color: #e0e7ff;
    }
    .warning-box {
        background-color: #451a03;
        border-left: 4px solid #f59e0b;
        padding: 1rem;
        margin-bottom: 1rem;
        border-radius: 0.5rem;
        color: #fef3c7;
    }
    .chat-message {
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
    }
    .user-message {
        background-color: #6366f1;
        color: white;
        margin-left: 20%;
    }
    .assistant-message {
        background-color: #1f2937;
        color: #e5e7eb;
        margin-right: 20%;
    }
    .refusal-message {
        background-color: #374151;
        border: 1px solid #f59e0b;
        color: #e5e7eb;
        margin-right: 20%;
    }
    .source-link {
        color: #818cf8;
        text-decoration: none;
        font-size: 0.875rem;
    }
    .source-link:hover {
        text-decoration: underline;
    }
    .fund-card {
        background-color: #1f2937;
        padding: 0.75rem;
        border-radius: 0.5rem;
        margin-bottom: 0.5rem;
        cursor: pointer;
        border: 1px solid transparent;
        transition: all 0.2s;
    }
    .fund-card:hover {
        border-color: #6366f1;
    }
    .stButton button {
        width: 100%;
        text-align: left;
        background-color: #1f2937;
        color: #e5e7eb;
        border: 1px solid #374151;
    }
    .stButton button:hover {
        border-color: #6366f1;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # Header
    st.markdown('<div class="main-header">💰 Mutual Fund FAQ Chatbot</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Get factual information about HDFC mutual funds</div>', unsafe_allow_html=True)
    
    # Disclaimers
    st.markdown("""
    <div class="disclaimer-box">
        <strong>ℹ️ Facts-Only Assistant:</strong> This chatbot provides factual information about HDFC mutual funds on INDMoney. 
        It does not provide investment advice or handle personal/account-specific queries.
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="warning-box">
        <strong>⚠️ Disclaimer:</strong> Past performance is not indicative of future returns. 
        Please read all scheme-related documents carefully before investing.
    </div>
    """, unsafe_allow_html=True)
    
    # Initialize session state
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Hello! I'm your Mutual Fund FAQ Assistant. I can help you with factual information about HDFC mutual funds on INDMoney. What would you like to know?",
                "sources": [],
                "is_refusal": False
            }
        ]
    
    # Load data
    funds = load_funds()
    chunks, embeddings = get_vector_store()
    model = get_embedding_model()
    
    # Check if data is available
    if chunks is None or embeddings is None:
        st.error("⚠️ Data not found. Please ensure the data files are present in the data/phase2 directory.")
        st.info("Run the Phase 2 indexer first to generate embeddings.")
        return
    
    # Layout
    col1, col2 = st.columns([1, 3])
    
    # Sidebar - Fund List
    with col1:
        st.subheader("📊 Available Funds")
        st.caption("Click to ask about a fund")
        
        for fund in funds:
            if st.button(
                f"{fund['name'][:30]}..." if len(fund['name']) > 30 else fund['name'],
                key=fund['scheme_id'],
                help=f"Risk: {fund['overview'].get('risk', 'N/A')}"
            ):
                st.session_state.input_question = f"Tell me about {fund['name']}"
                st.rerun()
        
        st.divider()
        st.subheader("💡 Suggested Questions")
        suggestions = [
            "What is the NAV of HDFC Flexi Cap Fund?",
            "What is the expense ratio?",
            "What is exit load?",
            "Tell me about the risk profile",
            "What is the minimum investment?"
        ]
        for suggestion in suggestions:
            if st.button(suggestion, key=f"sugg_{suggestion[:20]}"):
                st.session_state.input_question = suggestion
                st.rerun()
    
    # Main Chat Area
    with col2:
        # Chat messages
        for message in st.session_state.messages:
            message_class = "user-message" if message["role"] == "user" else "assistant-message"
            if message.get("is_refusal"):
                message_class = "refusal-message"
            
            st.markdown(f'<div class="chat-message {message_class}">{message["content"]}</div>', unsafe_allow_html=True)
            
            # Show sources for assistant messages
            if message["role"] == "assistant" and message.get("sources"):
                with st.expander("📎 Sources"):
                    for source in message["sources"]:
                        st.markdown(f'<a href="{source}" target="_blank" class="source-link">{source}</a>', unsafe_allow_html=True)
        
        # Input area
        st.divider()
        
        # Get input from session state or default
        default_input = st.session_state.get("input_question", "")
        
        col_input, col_button = st.columns([4, 1])
        
        with col_input:
            user_input = st.text_input(
                "Ask a question",
                value=default_input,
                placeholder="Ask about HDFC mutual funds...",
                label_visibility="collapsed",
                key="chat_input"
            )
        
        with col_button:
            send_button = st.button("Send 📤", use_container_width=True)
        
        # Handle send
        if send_button and user_input.strip():
            # Add user message
            st.session_state.messages.append({
                "role": "user",
                "content": user_input,
                "sources": [],
                "is_refusal": False
            })
            
            # Clear input
            st.session_state.input_question = ""
            
            # Show spinner while processing
            with st.spinner("Thinking..."):
                try:
                    response = rag_query(user_input, chunks, embeddings, model)
                    
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": response.answer,
                        "sources": response.sources,
                        "is_refusal": response.metadata.get("is_refusal", False)
                    })
                except Exception as e:
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"Sorry, I encountered an error: {str(e)}",
                        "sources": [],
                        "is_refusal": False
                    })
            
            st.rerun()

if __name__ == "__main__":
    main()
