#!/usr/bin/env python3
"""
Test script for Phase 3 RAG components without Groq API.
Tests query classification and retrieval independently.
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from phase3.phase3_rag_engine import (
    QueryClassifier, 
    QueryIntent,
    RetrievalEngine
)
from phase2.phase2_indexer import SimpleVectorStore, EmbeddingGenerator


def test_query_classifier():
    """Test the query classifier."""
    print("=" * 60)
    print("Testing Query Classifier")
    print("=" * 60)
    
    classifier = QueryClassifier()
    
    test_queries = [
        # Fund-fact queries
        ("What is the NAV of HDFC Flexi Cap Fund?", QueryIntent.FUND_FACT),
        ("Tell me about HDFC Small Cap Fund expense ratio", QueryIntent.FUND_FACT),
        
        # Concept queries
        ("What is exit load?", QueryIntent.CONCEPT_EXPLANATION),
        ("Explain expense ratio", QueryIntent.CONCEPT_EXPLANATION),
        
        # Advisory queries (should be refused)
        ("Should I buy HDFC Defence Fund?", QueryIntent.OPINION_ADVISORY),
        ("Which fund is best for me?", QueryIntent.OPINION_ADVISORY),
        ("Is HDFC Flexi Cap a good investment?", QueryIntent.OPINION_ADVISORY),
        
        # Personal queries (should be refused)
        ("What is my SIP amount?", QueryIntent.PERSONAL_ACCOUNT),
        ("Check my KYC status", QueryIntent.PERSONAL_ACCOUNT),
        ("My portfolio returns", QueryIntent.PERSONAL_ACCOUNT),
    ]
    
    for query, expected_intent in test_queries:
        result = classifier.classify(query)
        status = "✓" if result.intent == expected_intent else "✗"
        print(f"\n{status} Query: {query}")
        print(f"  Intent: {result.intent.value}")
        print(f"  Confidence: {result.confidence}")
        print(f"  Schemes: {result.mentioned_schemes}")
        print(f"  Is Refusal: {result.is_refusal}")


def test_retrieval():
    """Test the retrieval engine."""
    print("\n" + "=" * 60)
    print("Testing Retrieval Engine")
    print("=" * 60)
    
    # Initialize components
    print("\nLoading vector store...")
    vector_store = SimpleVectorStore(Path("data/phase2"))
    if not vector_store.load():
        print("ERROR: Vector store not found. Run Phase 2 indexer first.")
        return
    
    print("Loading embedding model...")
    embedding_generator = EmbeddingGenerator()
    
    retrieval_engine = RetrievalEngine(vector_store, embedding_generator)
    
    test_queries = [
        "What is the NAV of HDFC Flexi Cap Fund?",
        "expense ratio",
        "risk profile of HDFC Small Cap",
        "minimum investment amount",
    ]
    
    for query in test_queries:
        print(f"\nQuery: {query}")
        results = retrieval_engine.retrieve(query, top_k=3)
        
        for i, result in enumerate(results, 1):
            print(f"  {i}. {result['scheme_name']} ({result['chunk_type']}) - Score: {result['similarity']:.4f}")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Phase 3 Component Testing (without Groq API)")
    print("=" * 60)
    
    test_query_classifier()
    test_retrieval()
    
    print("\n" + "=" * 60)
    print("Component testing complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
