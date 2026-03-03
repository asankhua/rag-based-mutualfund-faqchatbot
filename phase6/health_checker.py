#!/usr/bin/env python3
"""
Health Checker / Smoke Test for Phase 6

Validates the pipeline after refresh:
- Tests canned queries against the RAG pipeline
- Validates answers are non-empty
- Validates source links are present
- Checks data freshness
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass, field

import sys
sys.path.append(str(Path(__file__).parent.parent))

from phase3.phase3_rag_engine import RAGPipeline
from phase2.phase2_indexer import SimpleVectorStore

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a health check test."""
    test_name: str
    passed: bool
    query: str
    answer: str = ""
    sources: List[str] = field(default_factory=list)
    error: Optional[str] = None
    response_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthCheckReport:
    """Complete health check report."""
    timestamp: str
    overall_status: str  # "healthy", "degraded", "failed"
    total_tests: int
    passed_tests: int
    failed_tests: int
    results: List[HealthCheckResult] = field(default_factory=list)
    data_freshness: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


class HealthChecker:
    """
    Health checker for validating the RAG pipeline after data refresh.
    
    Runs canned queries and validates:
    - Answers are non-empty
    - Source links are present
    - Data is fresh (scraped within acceptable timeframe)
    """
    
    # Canned test queries
    TEST_QUERIES = [
        {
            "name": "NAV Query - HDFC Flexi Cap",
            "query": "What is the NAV of HDFC Flexi Cap Fund?",
            "expected_keywords": ["NAV", "₹"],
            "min_sources": 1
        },
        {
            "name": "Expense Ratio Query - HDFC Small Cap",
            "query": "What is the expense ratio of HDFC Small Cap Fund?",
            "expected_keywords": ["expense ratio"],
            "min_sources": 1
        },
        {
            "name": "Returns Query - HDFC Focused",
            "query": "What are the returns of HDFC Focused Fund?",
            "expected_keywords": ["returns", "%"],
            "min_sources": 1
        },
        {
            "name": "Risk Query - HDFC Defence",
            "query": "What is the risk profile of HDFC Defence Fund?",
            "expected_keywords": ["risk"],
            "min_sources": 1
        },
        {
            "name": "AUM Query - HDFC Mid Cap",
            "query": "What is the AUM of HDFC Mid Cap Fund?",
            "expected_keywords": ["AUM", "₹"],
            "min_sources": 1
        },
        {
            "name": "Advisory Refusal Test",
            "query": "Should I buy HDFC Flexi Cap Fund?",
            "expected_keywords": ["cannot provide", "advice", "recommendation"],
            "min_sources": 1,
            "is_refusal": True
        },
        {
            "name": "Personal Query Refusal Test",
            "query": "What is my SIP amount?",
            "expected_keywords": ["unable", "personal", "account"],
            "min_sources": 1,
            "is_refusal": True
        }
    ]
    
    # Maximum acceptable data age (in hours)
    MAX_DATA_AGE_HOURS = 48
    
    def __init__(
        self,
        data_dir: Path = None,
        vector_store_dir: Path = None,
        groq_api_key: Optional[str] = None
    ):
        """
        Initialize the health checker.
        
        Args:
            data_dir: Directory containing Phase 1 data
            vector_store_dir: Directory containing Phase 2 embeddings
            groq_api_key: Optional Groq API key
        """
        project_root = Path(__file__).parent.parent
        
        self.data_dir = data_dir or (project_root / "data" / "phase1")
        self.vector_store_dir = vector_store_dir or (project_root / "data" / "phase2")
        
        self.rag_pipeline: Optional[RAGPipeline] = None
        self._groq_api_key = groq_api_key
        
        logger.info("HealthChecker initialized")
    
    def _init_rag_pipeline(self) -> RAGPipeline:
        """Initialize the RAG pipeline for testing."""
        if self.rag_pipeline is None:
            logger.info("Initializing RAG pipeline for health check...")
            self.rag_pipeline = RAGPipeline(
                groq_api_key=self._groq_api_key,
                vector_store_dir=self.vector_store_dir
            )
        return self.rag_pipeline
    
    def _check_data_freshness(self) -> Dict[str, Any]:
        """Check if the data is fresh (recently scraped)."""
        freshness_report = {
            "status": "unknown",
            "funds_checked": 0,
            "fresh_funds": 0,
            "stale_funds": 0,
            "oldest_scrape": None,
            "newest_scrape": None,
            "details": []
        }
        
        if not self.data_dir.exists():
            freshness_report["status"] = "error"
            freshness_report["error"] = f"Data directory not found: {self.data_dir}"
            return freshness_report
        
        now = datetime.utcnow()
        max_age = timedelta(hours=self.MAX_DATA_AGE_HOURS)
        
        scrape_times = []
        
        for json_file in self.data_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                scheme_id = data.get("scheme_id", json_file.stem)
                scraped_at_str = data.get("last_scraped_at")
                
                if scraped_at_str:
                    # Parse ISO format timestamp
                    scraped_at = datetime.fromisoformat(scraped_at_str.replace("Z", "+00:00"))
                    scraped_at = scraped_at.replace(tzinfo=None)  # Make naive for comparison
                    age = now - scraped_at
                    is_fresh = age <= max_age
                    
                    scrape_times.append(scraped_at)
                    
                    freshness_report["funds_checked"] += 1
                    if is_fresh:
                        freshness_report["fresh_funds"] += 1
                    else:
                        freshness_report["stale_funds"] += 1
                    
                    freshness_report["details"].append({
                        "scheme_id": scheme_id,
                        "scraped_at": scraped_at_str,
                        "age_hours": age.total_seconds() / 3600,
                        "is_fresh": is_fresh
                    })
            except Exception as e:
                logger.warning(f"Could not check freshness for {json_file}: {e}")
        
        if scrape_times:
            freshness_report["oldest_scrape"] = min(scrape_times).isoformat()
            freshness_report["newest_scrape"] = max(scrape_times).isoformat()
            
            # Determine overall freshness status
            if freshness_report["stale_funds"] == 0:
                freshness_report["status"] = "fresh"
            elif freshness_report["fresh_funds"] > 0:
                freshness_report["status"] = "partial"
            else:
                freshness_report["status"] = "stale"
        
        return freshness_report
    
    def _run_single_test(self, test_config: Dict[str, Any]) -> HealthCheckResult:
        """Run a single health check test."""
        import time
        
        test_name = test_config["name"]
        query = test_config["query"]
        expected_keywords = test_config.get("expected_keywords", [])
        min_sources = test_config.get("min_sources", 1)
        is_refusal = test_config.get("is_refusal", False)
        
        logger.info(f"Running test: {test_name}")
        
        start_time = time.time()
        
        try:
            pipeline = self._init_rag_pipeline()
            response = pipeline.query(query)
            
            response_time_ms = (time.time() - start_time) * 1000
            
            # Validate response
            errors = []
            
            # Check answer is non-empty
            if not response.answer or len(response.answer.strip()) < 10:
                errors.append("Answer is empty or too short")
            
            # Check sources are present
            if len(response.sources) < min_sources:
                errors.append(f"Expected at least {min_sources} source(s), got {len(response.sources)}")
            
            # Check expected keywords (for non-refusal queries)
            if not is_refusal:
                answer_lower = response.answer.lower()
                missing_keywords = [
                    kw for kw in expected_keywords
                    if kw.lower() not in answer_lower
                ]
                if missing_keywords:
                    errors.append(f"Missing expected keywords: {missing_keywords}")
            
            # Check refusal detection for advisory/personal queries
            if is_refusal:
                metadata = response.metadata or {}
                if not metadata.get("is_refusal", False):
                    errors.append("Expected refusal response but got regular answer")
            
            passed = len(errors) == 0
            
            return HealthCheckResult(
                test_name=test_name,
                passed=passed,
                query=query,
                answer=response.answer[:500] + "..." if len(response.answer) > 500 else response.answer,
                sources=response.sources,
                error="; ".join(errors) if errors else None,
                response_time_ms=response_time_ms,
                metadata={
                    "intent": response.metadata.get("intent"),
                    "is_refusal": response.metadata.get("is_refusal", False),
                    "chunks_retrieved": response.metadata.get("chunks_retrieved", 0)
                }
            )
            
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            logger.error(f"Test '{test_name}' failed with error: {e}")
            
            return HealthCheckResult(
                test_name=test_name,
                passed=False,
                query=query,
                error=str(e),
                response_time_ms=response_time_ms
            )
    
    def run_health_check(self) -> HealthCheckReport:
        """
        Run the complete health check suite.
        
        Returns:
            HealthCheckReport with all test results
        """
        timestamp = datetime.utcnow().isoformat() + "Z"
        logger.info("=" * 60)
        logger.info("Starting Health Check / Smoke Test")
        logger.info("=" * 60)
        
        results: List[HealthCheckResult] = []
        errors: List[str] = []
        
        # Step 1: Check data freshness
        logger.info("Checking data freshness...")
        data_freshness = self._check_data_freshness()
        
        if data_freshness["status"] == "error":
            errors.append(f"Data freshness check failed: {data_freshness.get('error')}")
        elif data_freshness["status"] == "stale":
            errors.append("All data is stale (older than 48 hours)")
        
        # Step 2: Run RAG tests
        logger.info(f"Running {len(self.TEST_QUERIES)} test queries...")
        
        for test_config in self.TEST_QUERIES:
            try:
                result = self._run_single_test(test_config)
                results.append(result)
                
                status = "PASSED" if result.passed else "FAILED"
                logger.info(f"  [{status}] {result.test_name} ({result.response_time_ms:.0f}ms)")
                
            except Exception as e:
                logger.error(f"  [ERROR] {test_config['name']}: {e}")
                errors.append(f"Test '{test_config['name']}' error: {e}")
                results.append(HealthCheckResult(
                    test_name=test_config["name"],
                    passed=False,
                    query=test_config["query"],
                    error=str(e)
                ))
        
        # Calculate overall status
        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        
        if failed_count == 0 and data_freshness["status"] in ["fresh", "partial"]:
            overall_status = "healthy"
        elif passed_count >= len(results) * 0.7:
            overall_status = "degraded"
        else:
            overall_status = "failed"
        
        report = HealthCheckReport(
            timestamp=timestamp,
            overall_status=overall_status,
            total_tests=len(results),
            passed_tests=passed_count,
            failed_tests=failed_count,
            results=results,
            data_freshness=data_freshness,
            errors=errors
        )
        
        logger.info("=" * 60)
        logger.info(f"Health Check Complete - Status: {overall_status.upper()}")
        logger.info(f"  Passed: {passed_count}/{len(results)}")
        logger.info(f"  Data freshness: {data_freshness['status']}")
        logger.info("=" * 60)
        
        return report
    
    def save_report(self, report: HealthCheckReport, output_path: Optional[Path] = None) -> Path:
        """Save the health check report to a JSON file."""
        if output_path is None:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            output_path = Path(__file__).parent.parent / "data" / "health_reports"
            output_path.mkdir(parents=True, exist_ok=True)
            output_path = output_path / f"health_report_{timestamp}.json"
        
        # Convert dataclass to dict
        report_dict = {
            "timestamp": report.timestamp,
            "overall_status": report.overall_status,
            "total_tests": report.total_tests,
            "passed_tests": report.passed_tests,
            "failed_tests": report.failed_tests,
            "data_freshness": report.data_freshness,
            "errors": report.errors,
            "results": [
                {
                    "test_name": r.test_name,
                    "passed": r.passed,
                    "query": r.query,
                    "answer": r.answer,
                    "sources": r.sources,
                    "error": r.error,
                    "response_time_ms": r.response_time_ms,
                    "metadata": r.metadata
                }
                for r in report.results
            ]
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Health report saved to: {output_path}")
        return output_path
