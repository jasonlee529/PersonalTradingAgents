# src/orchestrator/state.py
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class AnalysisStep(BaseModel):
    step_id: str
    label: str
    role: str
    character: str
    module: str = ""
    action: str = ""
    artifact_key: str = ""
    status: StepStatus = StepStatus.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    detail: str = ""


class AnalysisJob(BaseModel):
    id: str
    symbol: str
    status: JobStatus = JobStatus.PENDING
    phase: str = ""  # current step_id, e.g. "analyst_market"
    progress: str = ""
    result_summary: str = ""
    error: str = ""
    output_files: list[str] = Field(default_factory=list)
    steps: list[AnalysisStep] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    config: Optional[dict] = None  # stores analysts, overrides, position etc.
    retry_count: int = 0
    max_retries: int = 1

    def start(self) -> None:
        self.status = JobStatus.RUNNING
        self.started_at = datetime.now()

    def update_progress(self, msg: str) -> None:
        self.progress = msg

    def complete(self, summary: str = "") -> None:
        self.status = JobStatus.DONE
        self.result_summary = summary
        self.completed_at = datetime.now()

    def fail(self, error: str) -> None:
        self.status = JobStatus.ERROR
        self.error = error
        self.completed_at = datetime.now()

    def retry(self) -> None:
        """Reset job to pending for another attempt (preserves checkpoint if enabled)."""
        self.status = JobStatus.PENDING
        self.retry_count += 1
        self.error = ""
        self.started_at = None
        self.completed_at = None
        for step in self.steps:
            if step.status == StepStatus.ERROR:
                step.status = StepStatus.PENDING
                step.detail = ""
                step.started_at = None
                step.completed_at = None

    def derive_status(self) -> JobStatus:
        """Derive job status from steps. If any step errors, job is error.
        If all steps done, job is done. If any step running, job is running."""
        if not self.steps:
            return self.status
        if any(s.status == StepStatus.ERROR for s in self.steps):
            return JobStatus.ERROR
        if all(s.status == StepStatus.DONE for s in self.steps):
            return JobStatus.DONE
        if any(s.status == StepStatus.RUNNING for s in self.steps):
            return JobStatus.RUNNING
        return JobStatus.PENDING
