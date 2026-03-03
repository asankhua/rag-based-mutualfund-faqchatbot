#!/usr/bin/env python3
"""
Pipeline Scheduler for Phase 6

Manages scheduled jobs for:
- Daily scraping at 9 AM (Monday-Friday)
- Chunk/embedding rebuild for updated funds
- Health check / smoke test after refresh
"""

import logging
from datetime import datetime
from typing import Optional, Callable
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, JobExecutionEvent

logger = logging.getLogger(__name__)


class PipelineScheduler:
    """
    Scheduler for automated pipeline execution.
    
    Configured to run at 9:00 AM, Monday through Friday (trading days).
    """
    
    # Default schedule: 9:00 AM, Monday-Friday
    DEFAULT_HOUR = 9
    DEFAULT_MINUTE = 0
    DEFAULT_DAY_OF_WEEK = "mon-fri"
    
    def __init__(
        self,
        hour: int = DEFAULT_HOUR,
        minute: int = DEFAULT_MINUTE,
        day_of_week: str = DEFAULT_DAY_OF_WEEK,
        timezone: str = "Asia/Kolkata"  # IST for Indian market
    ):
        """
        Initialize the pipeline scheduler.
        
        Args:
            hour: Hour to run (0-23)
            minute: Minute to run (0-59)
            day_of_week: Days to run (cron format, e.g., "mon-fri")
            timezone: Timezone for scheduling
        """
        self.hour = hour
        self.minute = minute
        self.day_of_week = day_of_week
        self.timezone = timezone
        
        self.scheduler = BackgroundScheduler(timezone=timezone)
        self._setup_event_listeners()
        
        self._scrape_job_id = "daily_scrape"
        self._health_check_job_id = "health_check"
        
        self._scrape_callback: Optional[Callable] = None
        self._health_check_callback: Optional[Callable] = None
        
        logger.info(f"PipelineScheduler initialized (timezone: {timezone})")
    
    def _setup_event_listeners(self):
        """Setup event listeners for job execution monitoring."""
        self.scheduler.add_listener(
            self._on_job_executed,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR
        )
    
    def _on_job_executed(self, event: JobExecutionEvent):
        """Handle job execution events."""
        if event.exception:
            logger.error(f"Job {event.job_id} failed: {event.exception}")
        else:
            logger.info(f"Job {event.job_id} completed successfully")
    
    def register_scrape_callback(self, callback: Callable):
        """Register the callback for scrape jobs."""
        self._scrape_callback = callback
        logger.info("Scrape callback registered")
    
    def register_health_check_callback(self, callback: Callable):
        """Register the callback for health check jobs."""
        self._health_check_callback = callback
        logger.info("Health check callback registered")
    
    def _run_scrape_job(self):
        """Execute the scrape job."""
        logger.info("=" * 60)
        logger.info("Starting scheduled scrape job")
        logger.info("=" * 60)
        
        if self._scrape_callback:
            try:
                result = self._scrape_callback()
                logger.info(f"Scrape job completed: {result}")
                return result
            except Exception as e:
                logger.error(f"Scrape job failed: {e}")
                raise
        else:
            logger.warning("No scrape callback registered")
    
    def _run_health_check_job(self):
        """Execute the health check job."""
        logger.info("=" * 60)
        logger.info("Starting scheduled health check job")
        logger.info("=" * 60)
        
        if self._health_check_callback:
            try:
                result = self._health_check_callback()
                logger.info(f"Health check job completed: {result}")
                return result
            except Exception as e:
                logger.error(f"Health check job failed: {e}")
                raise
        else:
            logger.warning("No health check callback registered")
    
    def setup_jobs(self):
        """Setup scheduled jobs."""
        # Main scrape job - runs at 9 AM on weekdays
        self.scheduler.add_job(
            func=self._run_scrape_job,
            trigger=CronTrigger(
                hour=self.hour,
                minute=self.minute,
                day_of_week=self.day_of_week
            ),
            id=self._scrape_job_id,
            name="Daily Fund Data Scrape",
            replace_existing=True,
            misfire_grace_time=3600  # 1 hour grace period
        )
        
        # Health check job - runs 30 minutes after scrape
        self.scheduler.add_job(
            func=self._run_health_check_job,
            trigger=CronTrigger(
                hour=self.hour,
                minute=self.minute + 30,
                day_of_week=self.day_of_week
            ),
            id=self._health_check_job_id,
            name="Health Check / Smoke Test",
            replace_existing=True,
            misfire_grace_time=1800  # 30 minutes grace period
        )
        
        logger.info("Scheduled jobs configured:")
        logger.info(f"  - Scrape job: {self.hour:02d}:{self.minute:02d}, {self.day_of_week}")
        logger.info(f"  - Health check: {self.hour:02d}:{self.minute + 30:02d}, {self.day_of_week}")
    
    def start(self):
        """Start the scheduler."""
        self.setup_jobs()
        self.scheduler.start()
        logger.info("Scheduler started")
        
        # Log next run times
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time
            logger.info(f"  Next run for '{job.id}': {next_run}")
    
    def shutdown(self, wait: bool = True):
        """Shutdown the scheduler."""
        self.scheduler.shutdown(wait=wait)
        logger.info("Scheduler shutdown")
    
    def get_job_status(self) -> dict:
        """Get status of all scheduled jobs."""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })
        
        return {
            "scheduler_running": self.scheduler.running,
            "timezone": str(self.scheduler.timezone),
            "jobs": jobs
        }
    
    def run_scrape_now(self):
        """Manually trigger a scrape job immediately."""
        logger.info("Manually triggering scrape job")
        return self._run_scrape_job()
    
    def run_health_check_now(self):
        """Manually trigger a health check job immediately."""
        logger.info("Manually triggering health check job")
        return self._run_health_check_job()
