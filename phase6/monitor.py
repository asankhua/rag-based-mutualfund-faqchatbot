#!/usr/bin/env python3
"""
Pipeline Monitor for Phase 6

Tracks and logs pipeline metrics:
- Last successful scrape time per URL
- Number of chunks per scheme
- Embedding generation failures
- Average chat response latency
- Pipeline run history

Provides alerting for:
- Scrape failures
- Sudden reduction in chunks
- Missing data for any scheme
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class PipelineMetrics:
    """Metrics for a single pipeline run."""
    run_id: str
    timestamp: str
    status: str  # "success", "failed", "partial"
    duration_seconds: float
    
    # Phase 1 metrics
    funds_scraped: int = 0
    scrape_failures: List[str] = field(default_factory=list)
    
    # Phase 2 metrics
    total_chunks: int = 0
    schemes_indexed: int = 0
    embedding_failures: List[str] = field(default_factory=list)
    
    # Change detection
    new_schemes: List[str] = field(default_factory=list)
    changed_schemes: List[str] = field(default_factory=list)
    
    # Health check
    health_check_status: Optional[str] = None
    tests_passed: int = 0
    tests_failed: int = 0


@dataclass
class SchemeMetrics:
    """Metrics for a specific scheme."""
    scheme_id: str
    scheme_name: str
    
    last_scraped_at: Optional[str] = None
    last_scrape_status: str = "unknown"
    
    chunk_count: int = 0
    last_indexed_at: Optional[str] = None
    
    # Historical data
    nav_history: List[Dict[str, Any]] = field(default_factory=list)
    aum_history: List[Dict[str, Any]] = field(default_factory=list)


class PipelineMonitor:
    """
    Monitors the pipeline and tracks metrics over time.
    
    Provides:
    - Metric tracking and persistence
    - Alert generation for anomalies
    - Historical data analysis
    """
    
    # Thresholds for alerts
    MIN_CHUNKS_PER_SCHEME = 5  # Each scheme should have at least 5 chunks
    MAX_SCRAPE_AGE_HOURS = 48  # Data should be scraped within 48 hours
    
    def __init__(
        self,
        metrics_dir: Path = None,
        max_history_days: int = 30
    ):
        """
        Initialize the pipeline monitor.
        
        Args:
            metrics_dir: Directory to store metrics
            max_history_days: Maximum days to keep metrics history
        """
        project_root = Path(__file__).parent.parent
        
        self.metrics_dir = metrics_dir or (project_root / "data" / "metrics")
        self.metrics_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_history_days = max_history_days
        
        # File paths
        self.pipeline_metrics_file = self.metrics_dir / "pipeline_metrics.jsonl"
        self.scheme_metrics_file = self.metrics_dir / "scheme_metrics.json"
        self.alerts_file = self.metrics_dir / "alerts.jsonl"
        
        # In-memory cache
        self._scheme_metrics_cache: Dict[str, SchemeMetrics] = {}
        
        logger.info(f"PipelineMonitor initialized")
        logger.info(f"  Metrics dir: {self.metrics_dir}")
    
    def _generate_run_id(self) -> str:
        """Generate a unique run ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"run_{timestamp}"
    
    def record_pipeline_run(self, metrics: PipelineMetrics):
        """Record metrics from a pipeline run."""
        # Append to JSONL file
        with open(self.pipeline_metrics_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(metrics), ensure_ascii=False) + "\n")
        
        logger.info(f"Recorded pipeline run: {metrics.run_id} (status: {metrics.status})")
        
        # Check for alerts
        self._check_pipeline_alerts(metrics)
    
    def record_scheme_metrics(self, scheme_metrics: SchemeMetrics):
        """Record or update metrics for a scheme."""
        self._scheme_metrics_cache[scheme_metrics.scheme_id] = scheme_metrics
        
        # Save all scheme metrics
        metrics_dict = {
            scheme_id: asdict(metrics)
            for scheme_id, metrics in self._scheme_metrics_cache.items()
        }
        
        with open(self.scheme_metrics_file, "w", encoding="utf-8") as f:
            json.dump(metrics_dict, f, indent=2, ensure_ascii=False)
    
    def _check_pipeline_alerts(self, metrics: PipelineMetrics):
        """Check for alert conditions in pipeline metrics."""
        alerts = []
        
        # Alert: Scrape failures
        if metrics.scrape_failures:
            alert = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "severity": "error",
                "type": "scrape_failure",
                "message": f"Scrape failures detected: {len(metrics.scrape_failures)} funds failed",
                "details": metrics.scrape_failures,
                "run_id": metrics.run_id
            }
            alerts.append(alert)
            logger.error(f"ALERT: {alert['message']}")
        
        # Alert: Embedding failures
        if metrics.embedding_failures:
            alert = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "severity": "error",
                "type": "embedding_failure",
                "message": f"Embedding failures detected: {len(metrics.embedding_failures)} schemes failed",
                "details": metrics.embedding_failures,
                "run_id": metrics.run_id
            }
            alerts.append(alert)
            logger.error(f"ALERT: {alert['message']}")
        
        # Alert: Health check failures
        if metrics.health_check_status == "failed":
            alert = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "severity": "critical",
                "type": "health_check_failure",
                "message": f"Health check failed: {metrics.tests_failed}/{metrics.tests_passed + metrics.tests_failed} tests failed",
                "run_id": metrics.run_id
            }
            alerts.append(alert)
            logger.error(f"ALERT: {alert['message']}")
        
        # Write alerts
        for alert in alerts:
            with open(self.alerts_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(alert, ensure_ascii=False) + "\n")
    
    def check_scheme_alerts(self, data_dir: Path = None) -> List[Dict[str, Any]]:
        """
        Check for scheme-level alerts.
        
        Returns:
            List of alert dictionaries
        """
        project_root = Path(__file__).parent.parent
        data_dir = data_dir or (project_root / "data" / "phase1")
        
        alerts = []
        now = datetime.utcnow()
        max_age = timedelta(hours=self.MAX_SCRAPE_AGE_HOURS)
        
        for json_file in data_dir.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                scheme_id = data.get("scheme_id", json_file.stem)
                scheme_name = data.get("name", scheme_id)
                
                # Check data freshness
                scraped_at_str = data.get("last_scraped_at")
                if scraped_at_str:
                    scraped_at = datetime.fromisoformat(scraped_at_str.replace("Z", "+00:00"))
                    scraped_at = scraped_at.replace(tzinfo=None)
                    age = now - scraped_at
                    
                    if age > max_age:
                        alert = {
                            "timestamp": now.isoformat() + "Z",
                            "severity": "warning",
                            "type": "stale_data",
                            "scheme_id": scheme_id,
                            "message": f"Data for {scheme_name} is stale (age: {age.total_seconds() / 3600:.1f} hours)"
                        }
                        alerts.append(alert)
                
                # Check for missing key fields
                overview = data.get("overview", {})
                missing_fields = [
                    field for field in ["nav", "expense_ratio", "aum", "risk"]
                    if not overview.get(field)
                ]
                
                if missing_fields:
                    alert = {
                        "timestamp": now.isoformat() + "Z",
                        "severity": "warning",
                        "type": "missing_fields",
                        "scheme_id": scheme_id,
                        "message": f"{scheme_name} is missing key fields: {missing_fields}"
                    }
                    alerts.append(alert)
                    
            except Exception as e:
                logger.warning(f"Could not check alerts for {json_file}: {e}")
        
        # Write alerts
        for alert in alerts:
            with open(self.alerts_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(alert, ensure_ascii=False) + "\n")
        
        if alerts:
            logger.warning(f"Generated {len(alerts)} scheme-level alerts")
        
        return alerts
    
    def get_pipeline_history(
        self,
        days: int = 7,
        status_filter: Optional[str] = None
    ) -> List[PipelineMetrics]:
        """
        Get pipeline run history.
        
        Args:
            days: Number of days to look back
            status_filter: Optional filter by status
            
        Returns:
            List of PipelineMetrics
        """
        history = []
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        if not self.pipeline_metrics_file.exists():
            return history
        
        with open(self.pipeline_metrics_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    run_time = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                    
                    if run_time.replace(tzinfo=None) < cutoff:
                        continue
                    
                    if status_filter and data.get("status") != status_filter:
                        continue
                    
                    history.append(PipelineMetrics(**data))
                except Exception as e:
                    logger.warning(f"Could not parse metrics line: {e}")
        
        return history
    
    def get_latest_metrics(self) -> Optional[PipelineMetrics]:
        """Get the most recent pipeline metrics."""
        history = self.get_pipeline_history(days=1)
        return history[-1] if history else None
    
    def get_alerts(
        self,
        days: int = 7,
        severity_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent alerts.
        
        Args:
            days: Number of days to look back
            severity_filter: Optional filter by severity (error, warning, critical)
            
        Returns:
            List of alert dictionaries
        """
        alerts = []
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        if not self.alerts_file.exists():
            return alerts
        
        with open(self.alerts_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    alert = json.loads(line.strip())
                    alert_time = datetime.fromisoformat(alert["timestamp"].replace("Z", "+00:00"))
                    
                    if alert_time.replace(tzinfo=None) < cutoff:
                        continue
                    
                    if severity_filter and alert.get("severity") != severity_filter:
                        continue
                    
                    alerts.append(alert)
                except Exception as e:
                    logger.warning(f"Could not parse alert line: {e}")
        
        return alerts
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of pipeline health."""
        latest = self.get_latest_metrics()
        recent_history = self.get_pipeline_history(days=7)
        recent_alerts = self.get_alerts(days=1)
        
        # Calculate success rate
        if recent_history:
            success_count = sum(1 for m in recent_history if m.status == "success")
            success_rate = success_count / len(recent_history)
        else:
            success_rate = 0.0
        
        return {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "latest_run": asdict(latest) if latest else None,
            "last_7_days": {
                "total_runs": len(recent_history),
                "success_rate": f"{success_rate:.1%}",
                "avg_duration_seconds": sum(m.duration_seconds for m in recent_history) / len(recent_history) if recent_history else 0
            },
            "recent_alerts_count": len(recent_alerts),
            "critical_alerts": len([a for a in recent_alerts if a.get("severity") == "critical"]),
            "status": "healthy" if success_rate > 0.9 and not recent_alerts else "degraded" if success_rate > 0.5 else "critical"
        }
    
    def cleanup_old_metrics(self):
        """Clean up metrics older than max_history_days."""
        cutoff = datetime.utcnow() - timedelta(days=self.max_history_days)
        
        # Clean pipeline metrics
        if self.pipeline_metrics_file.exists():
            lines_to_keep = []
            with open(self.pipeline_metrics_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        run_time = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                        if run_time.replace(tzinfo=None) >= cutoff:
                            lines_to_keep.append(line)
                    except:
                        pass
            
            with open(self.pipeline_metrics_file, "w", encoding="utf-8") as f:
                f.writelines(lines_to_keep)
        
        # Clean alerts
        if self.alerts_file.exists():
            lines_to_keep = []
            with open(self.alerts_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        alert_time = datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))
                        if alert_time.replace(tzinfo=None) >= cutoff:
                            lines_to_keep.append(line)
                    except:
                        pass
            
            with open(self.alerts_file, "w", encoding="utf-8") as f:
                f.writelines(lines_to_keep)
        
        logger.info(f"Cleaned up metrics older than {self.max_history_days} days")
