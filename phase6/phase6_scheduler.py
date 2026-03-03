#!/usr/bin/env python3
"""
Phase 6 - Scheduler & Auto-Refresh Pipeline

Main entry point for the automated pipeline scheduler.

Usage:
    # Run scheduler in background (starts at 9 AM weekdays)
    python -m phase6.phase6_scheduler
    
    # Run pipeline once immediately
    python -m phase6.phase6_scheduler --run-once
    
    # Run health check only
    python -m phase6.phase6_scheduler --health-check
    
    # Force full reindex
    python -m phase6.phase6_scheduler --run-once --force-reindex
    
    # Show status
    python -m phase6.phase6_scheduler --status
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

# Load environment variables
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from phase6.scheduler import PipelineScheduler
from phase6.orchestrator import PipelineOrchestrator
from phase6.health_checker import HealthChecker
from phase6.monitor import PipelineMonitor, PipelineMetrics


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            Path(__file__).parent.parent / "data" / "logs" / "phase6.log",
            mode='a'
        ) if (Path(__file__).parent.parent / "data" / "logs").exists() or (Path(__file__).parent.parent / "data" / "logs").mkdir(parents=True, exist_ok=True) else logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class Phase6Runner:
    """
    Main runner for Phase 6 scheduler and pipeline.
    
    Integrates:
    - PipelineScheduler: Manages scheduled job execution
    - PipelineOrchestrator: Runs Phase 1 → Phase 2 pipeline
    - HealthChecker: Validates pipeline after refresh
    - PipelineMonitor: Tracks metrics and generates alerts
    """
    
    def __init__(
        self,
        hour: int = 9,
        minute: int = 0,
        timezone: str = "Asia/Kolkata"
    ):
        """Initialize the Phase 6 runner."""
        self.scheduler = PipelineScheduler(
            hour=hour,
            minute=minute,
            timezone=timezone
        )
        self.orchestrator = PipelineOrchestrator()
        self.health_checker = HealthChecker()
        self.monitor = PipelineMonitor()
        
        # Register callbacks with scheduler
        self.scheduler.register_scrape_callback(self._run_pipeline)
        self.scheduler.register_health_check_callback(self._run_health_check)
        
        logger.info("Phase6Runner initialized")
    
    def _run_pipeline(self) -> dict:
        """
        Run the complete pipeline (called by scheduler).
        
        Returns:
            Pipeline results dictionary
        """
        run_id = self.monitor._generate_run_id()
        logger.info(f"Starting pipeline run: {run_id}")
        
        try:
            # Run the pipeline
            results = self.orchestrator.run(force_reindex=False)
            
            # Record metrics
            metrics = PipelineMetrics(
                run_id=run_id,
                timestamp=results.get("start_time", datetime.utcnow().isoformat() + "Z"),
                status="success" if not results.get("errors") else "partial",
                duration_seconds=results.get("duration_seconds", 0),
                funds_scraped=results.get("phase1", {}).get("total_scraped", 0),
                scrape_failures=[],  # Would be populated from results
                total_chunks=results.get("phase2", {}).get("total_chunks", 0),
                schemes_indexed=results.get("phase2", {}).get("schemes_indexed", 0),
                new_schemes=results.get("change_detection", {}).get("new_schemes", []),
                changed_schemes=results.get("change_detection", {}).get("changed_schemes", [])
            )
            
            self.monitor.record_pipeline_run(metrics)
            
            # Check for scheme-level alerts
            self.monitor.check_scheme_alerts()
            
            logger.info(f"Pipeline run {run_id} completed successfully")
            return results
            
        except Exception as e:
            logger.error(f"Pipeline run {run_id} failed: {e}")
            
            # Record failure metrics
            metrics = PipelineMetrics(
                run_id=run_id,
                timestamp=datetime.utcnow().isoformat() + "Z",
                status="failed",
                duration_seconds=0,
                scrape_failures=[str(e)]
            )
            self.monitor.record_pipeline_run(metrics)
            
            raise
    
    def _run_health_check(self) -> dict:
        """
        Run health check (called by scheduler).
        
        Returns:
            Health check report dictionary
        """
        logger.info("Running scheduled health check")
        
        try:
            report = self.health_checker.run_health_check()
            
            # Save report
            report_path = self.health_checker.save_report(report)
            
            # Update latest metrics with health check results
            latest_metrics = self.monitor.get_latest_metrics()
            if latest_metrics:
                latest_metrics.health_check_status = report.overall_status
                latest_metrics.tests_passed = report.passed_tests
                latest_metrics.tests_failed = report.failed_tests
                
                # Re-record with health check info
                self.monitor.record_pipeline_run(latest_metrics)
            
            logger.info(f"Health check completed: {report.overall_status}")
            return {
                "status": report.overall_status,
                "passed": report.passed_tests,
                "failed": report.failed_tests,
                "report_path": str(report_path)
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            raise
    
    def run_once(self, force_reindex: bool = False, skip_health_check: bool = False) -> dict:
        """
        Run the pipeline once immediately.
        
        Args:
            force_reindex: If True, reindex all funds regardless of changes
            skip_health_check: If True, skip the health check
            
        Returns:
            Combined results dictionary
        """
        logger.info("=" * 60)
        logger.info("Running Phase 6 Pipeline (One-time)")
        logger.info("=" * 60)
        
        results = {
            "pipeline": None,
            "health_check": None,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        # Run pipeline
        try:
            if force_reindex:
                logger.info("Force reindex enabled - will rebuild all embeddings")
            
            pipeline_results = self.orchestrator.run(force_reindex=force_reindex)
            results["pipeline"] = pipeline_results
            
        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}")
            results["pipeline_error"] = str(e)
        
        # Run health check
        if not skip_health_check:
            try:
                health_report = self.health_checker.run_health_check()
                self.health_checker.save_report(health_report)
                
                results["health_check"] = {
                    "status": health_report.overall_status,
                    "passed": health_report.passed_tests,
                    "failed": health_report.failed_tests
                }
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                results["health_check_error"] = str(e)
        
        return results
    
    def run_health_check_only(self) -> dict:
        """Run only the health check."""
        logger.info("Running health check only")
        return self._run_health_check()
    
    def start_scheduler(self):
        """Start the background scheduler."""
        logger.info("=" * 60)
        logger.info("Starting Phase 6 Scheduler")
        logger.info("=" * 60)
        logger.info("Schedule: 9:00 AM, Monday-Friday (IST)")
        logger.info("Press Ctrl+C to stop")
        logger.info("=" * 60)
        
        self.scheduler.start()
        
        # Keep the main thread alive
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\nShutting down scheduler...")
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")
    
    def get_status(self) -> dict:
        """Get current status of the scheduler and pipeline."""
        return {
            "scheduler": self.scheduler.get_job_status(),
            "pipeline": self.monitor.get_summary(),
            "last_run": self.orchestrator.get_last_run_results()
        }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Phase 6 - Scheduler & Auto-Refresh Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start scheduler (runs at 9 AM weekdays)
  python -m phase6.phase6_scheduler
  
  # Run pipeline once immediately
  python -m phase6.phase6_scheduler --run-once
  
  # Run with force reindex
  python -m phase6.phase6_scheduler --run-once --force-reindex
  
  # Run health check only
  python -m phase6.phase6_scheduler --health-check
  
  # Show current status
  python -m phase6.phase6_scheduler --status
        """
    )
    
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Run the pipeline once immediately and exit"
    )
    
    parser.add_argument(
        "--force-reindex",
        action="store_true",
        help="Force reindex of all funds (with --run-once)"
    )
    
    parser.add_argument(
        "--skip-health-check",
        action="store_true",
        help="Skip health check after pipeline run"
    )
    
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Run health check only"
    )
    
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show scheduler and pipeline status"
    )
    
    parser.add_argument(
        "--hour",
        type=int,
        default=9,
        help="Hour to run scheduled job (0-23, default: 9)"
    )
    
    parser.add_argument(
        "--minute",
        type=int,
        default=0,
        help="Minute to run scheduled job (0-59, default: 0)"
    )
    
    parser.add_argument(
        "--timezone",
        type=str,
        default="Asia/Kolkata",
        help="Timezone for scheduling (default: Asia/Kolkata)"
    )
    
    args = parser.parse_args()
    
    # Create runner
    runner = Phase6Runner(
        hour=args.hour,
        minute=args.minute,
        timezone=args.timezone
    )
    
    # Execute based on arguments
    if args.status:
        status = runner.get_status()
        print(json.dumps(status, indent=2, default=str))
        
    elif args.health_check:
        results = runner.run_health_check_only()
        print(json.dumps(results, indent=2, default=str))
        
    elif args.run_once:
        results = runner.run_once(
            force_reindex=args.force_reindex,
            skip_health_check=args.skip_health_check
        )
        print(json.dumps(results, indent=2, default=str))
        
    else:
        # Start scheduler
        runner.start_scheduler()


if __name__ == "__main__":
    main()
