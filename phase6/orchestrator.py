#!/usr/bin/env python3
"""
Pipeline Orchestrator for Phase 6

Orchestrates the complete pipeline:
- Phase 1: Scrape fund data from INDMoney
- Detect changes in fund data
- Phase 2: Rebuild chunks and embeddings for updated funds
- Update vector store
"""

import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional, Set
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).parent.parent))

from phase1.phase1_scraper import scrape_all_funds_async, ALLOWLISTED_URLS
from phase2.phase2_indexer import Phase2Indexer, SimpleVectorStore

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """
    Orchestrates the complete data refresh pipeline.
    
    Flow:
    1. Scrape all funds (Phase 1)
    2. Compare with previous data to detect changes
    3. Rebuild chunks and embeddings for changed funds (Phase 2)
    4. Update vector store
    """
    
    # Key fields that trigger a re-index when changed
    KEY_FIELDS = [
        "nav",
        "returns_since_inception",
        "returns_1y",
        "returns_3y",
        "returns_5y",
        "expense_ratio",
        "aum",
        "benchmark",
        "risk",
        "exit_load",
        "lock_in",
        "turnover",
        "min_lumpsum",
        "min_sip",
    ]
    
    def __init__(
        self,
        data_dir: Path = None,
        output_dir: Path = None,
        backup_dir: Path = None
    ):
        """
        Initialize the pipeline orchestrator.
        
        Args:
            data_dir: Directory for Phase 1 data (scraped fund JSON files)
            output_dir: Directory for Phase 2 output (chunks, embeddings)
            backup_dir: Directory for backing up previous data
        """
        project_root = Path(__file__).parent.parent
        
        self.data_dir = data_dir or (project_root / "data" / "phase1")
        self.output_dir = output_dir or (project_root / "data" / "phase2")
        self.backup_dir = backup_dir or (project_root / "data" / "backups")
        
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        self.indexer = Phase2Indexer()
        
        # Track pipeline results
        self.last_run_results: Optional[Dict[str, Any]] = None
        
        logger.info(f"PipelineOrchestrator initialized")
        logger.info(f"  Data dir: {self.data_dir}")
        logger.info(f"  Output dir: {self.output_dir}")
        logger.info(f"  Backup dir: {self.backup_dir}")
    
    def _load_previous_data(self, scheme_id: str) -> Optional[Dict[str, Any]]:
        """Load previous data for a scheme to compare changes."""
        json_file = self.data_dir / f"{scheme_id}.json"
        if not json_file.exists():
            return None
        
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load previous data for {scheme_id}: {e}")
            return None
    
    def _detect_changes(
        self,
        old_data: Optional[Dict[str, Any]],
        new_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Detect changes between old and new fund data.
        
        Returns:
            Dict with change information
        """
        changes = {
            "is_new": old_data is None,
            "has_changes": False,
            "changed_fields": [],
            "old_values": {},
            "new_values": {}
        }
        
        if old_data is None:
            changes["has_changes"] = True
            return changes
        
        old_overview = old_data.get("overview", {})
        new_overview = new_data.get("overview", {})
        
        for field in self.KEY_FIELDS:
            old_value = old_overview.get(field)
            new_value = new_overview.get(field)
            
            if old_value != new_value:
                changes["has_changes"] = True
                changes["changed_fields"].append(field)
                changes["old_values"][field] = old_value
                changes["new_values"][field] = new_value
        
        return changes
    
    def _backup_current_data(self) -> Path:
        """Backup current data before scraping."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"backup_{timestamp}"
        backup_path.mkdir(parents=True, exist_ok=True)
        
        # Backup Phase 1 data
        phase1_backup = backup_path / "phase1"
        phase1_backup.mkdir(exist_ok=True)
        
        if self.data_dir.exists():
            for json_file in self.data_dir.glob("*.json"):
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                with open(phase1_backup / json_file.name, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
        
        # Backup Phase 2 data
        phase2_backup = backup_path / "phase2"
        phase2_backup.mkdir(exist_ok=True)
        
        for file in ["chunks.json", "embeddings.npy", "metadata.json"]:
            src = self.output_dir / file
            if src.exists():
                import shutil
                shutil.copy2(src, phase2_backup / file)
        
        logger.info(f"Backup created at: {backup_path}")
        return backup_path
    
    async def run_pipeline(self, force_reindex: bool = False) -> Dict[str, Any]:
        """
        Run the complete pipeline.
        
        Args:
            force_reindex: If True, reindex all funds regardless of changes
            
        Returns:
            Dict with pipeline results
        """
        start_time = datetime.utcnow()
        logger.info("=" * 60)
        logger.info("Starting Pipeline Execution")
        logger.info("=" * 60)
        
        results = {
            "start_time": start_time.isoformat() + "Z",
            "status": "running",
            "phase1": {},
            "phase2": {},
            "errors": []
        }
        
        try:
            # Step 1: Backup current data
            logger.info("Step 1: Creating backup...")
            backup_path = self._backup_current_data()
            results["backup_path"] = str(backup_path)
            
            # Step 2: Scrape all funds (Phase 1)
            logger.info("Step 2: Running Phase 1 - Scraping fund data...")
            
            # Load previous data for comparison
            previous_data = {}
            for url in ALLOWLISTED_URLS:
                scheme_id = url.split("/")[-1]
                previous_data[scheme_id] = self._load_previous_data(scheme_id)
            
            # Scrape all funds
            scraped_files = await scrape_all_funds_async(str(self.data_dir))
            results["phase1"]["scraped_files"] = scraped_files
            results["phase1"]["total_scraped"] = len(scraped_files)
            
            # Step 3: Detect changes
            logger.info("Step 3: Detecting changes...")
            changed_schemes: Set[str] = set()
            new_schemes: Set[str] = set()
            change_details = {}
            
            for url in ALLOWLISTED_URLS:
                scheme_id = url.split("/")[-1]
                json_file = self.data_dir / f"{scheme_id}.json"
                
                if not json_file.exists():
                    continue
                
                with open(json_file, "r", encoding="utf-8") as f:
                    new_data = json.load(f)
                
                changes = self._detect_changes(previous_data.get(scheme_id), new_data)
                change_details[scheme_id] = changes
                
                if changes["is_new"]:
                    new_schemes.add(scheme_id)
                    logger.info(f"  New scheme detected: {scheme_id}")
                elif changes["has_changes"]:
                    changed_schemes.add(scheme_id)
                    logger.info(f"  Changes detected in {scheme_id}:")
                    for field in changes["changed_fields"]:
                        old_val = changes["old_values"].get(field, "N/A")
                        new_val = changes["new_values"].get(field, "N/A")
                        logger.info(f"    - {field}: {old_val} -> {new_val}")
            
            results["change_detection"] = {
                "new_schemes": list(new_schemes),
                "changed_schemes": list(changed_schemes),
                "unchanged_count": len(ALLOWLISTED_URLS) - len(new_schemes) - len(changed_schemes),
                "details": change_details
            }
            
            # Step 4: Rebuild chunks and embeddings (Phase 2)
            logger.info("Step 4: Running Phase 2 - Rebuilding chunks and embeddings...")
            
            schemes_to_index = list(new_schemes | changed_schemes) if not force_reindex else None
            
            if force_reindex:
                logger.info("  Force reindex: Rebuilding all funds")
                total_chunks = self.indexer.index_all_funds()
            elif schemes_to_index:
                logger.info(f"  Rebuilding {len(schemes_to_index)} changed funds")
                total_chunks = 0
                for scheme_id in schemes_to_index:
                    try:
                        chunks = self.indexer.index_fund(scheme_id)
                        total_chunks += chunks
                        logger.info(f"    Indexed {scheme_id}: {chunks} chunks")
                    except Exception as e:
                        error_msg = f"Failed to index {scheme_id}: {e}"
                        logger.error(error_msg)
                        results["errors"].append(error_msg)
            else:
                logger.info("  No changes detected, skipping reindex")
                total_chunks = 0
            
            self.indexer.vector_store.save()
            
            results["phase2"]["total_chunks"] = total_chunks
            results["phase2"]["schemes_indexed"] = len(schemes_to_index) if schemes_to_index else len(ALLOWLISTED_URLS)
            
            # Step 5: Finalize
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            results["end_time"] = end_time.isoformat() + "Z"
            results["duration_seconds"] = duration
            results["status"] = "completed" if not results["errors"] else "completed_with_errors"
            
            logger.info("=" * 60)
            logger.info("Pipeline Execution Complete")
            logger.info(f"  Duration: {duration:.2f} seconds")
            logger.info(f"  Scraped: {len(scraped_files)} funds")
            logger.info(f"  New schemes: {len(new_schemes)}")
            logger.info(f"  Changed schemes: {len(changed_schemes)}")
            logger.info(f"  Total chunks: {total_chunks}")
            logger.info("=" * 60)
            
            self.last_run_results = results
            return results
            
        except Exception as e:
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()
            
            results["end_time"] = end_time.isoformat() + "Z"
            results["duration_seconds"] = duration
            results["status"] = "failed"
            results["errors"].append(str(e))
            
            logger.error(f"Pipeline failed: {e}")
            raise
    
    def run(self, force_reindex: bool = False) -> Dict[str, Any]:
        """Synchronous wrapper for run_pipeline."""
        return asyncio.run(self.run_pipeline(force_reindex))
    
    def get_last_run_results(self) -> Optional[Dict[str, Any]]:
        """Get results from the last pipeline run."""
        return self.last_run_results
