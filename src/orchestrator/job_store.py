# src/orchestrator/job_store.py
from contextlib import asynccontextmanager
import json
import aiosqlite
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.orchestrator.state import AnalysisJob, JobStatus, AnalysisStep, StepStatus


SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_jobs (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    status TEXT NOT NULL,
    phase TEXT DEFAULT '',
    progress TEXT DEFAULT '',
    result_summary TEXT DEFAULT '',
    error TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    output_files TEXT DEFAULT '[]',
    steps_json TEXT DEFAULT '[]',
    config TEXT DEFAULT '{}',
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_symbol ON analysis_jobs(symbol);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_status ON analysis_jobs(status);
CREATE INDEX IF NOT EXISTS idx_analysis_jobs_created ON analysis_jobs(created_at);

CREATE TABLE IF NOT EXISTS analysis_step_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    feedback_type TEXT NOT NULL,
    comment TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    FOREIGN KEY (job_id) REFERENCES analysis_jobs(id)
);
CREATE INDEX IF NOT EXISTS idx_feedback_job ON analysis_step_feedback(job_id);
CREATE INDEX IF NOT EXISTS idx_feedback_step ON analysis_step_feedback(step_id);

CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 0,
    cron TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_MIGRATIONS = [
    "ALTER TABLE analysis_jobs ADD COLUMN config TEXT DEFAULT '{}'",
    "ALTER TABLE analysis_jobs ADD COLUMN phase TEXT DEFAULT ''",
    "ALTER TABLE analysis_jobs ADD COLUMN steps_json TEXT DEFAULT '[]'",
    "ALTER TABLE analysis_jobs ADD COLUMN retry_count INTEGER DEFAULT 0",
    "ALTER TABLE analysis_jobs ADD COLUMN max_retries INTEGER DEFAULT 1",
]


class JobStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    @asynccontextmanager
    async def _connect(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA busy_timeout = 5000")
            yield db

    async def init_db(self) -> None:
        async with self._connect() as db:
            await db.executescript(SCHEMA)
            await db.commit()
            # Enable WAL mode for better read/write concurrency
            await db.execute("PRAGMA journal_mode=WAL")
            await db.commit()
            # Run migrations
            for migration in _MIGRATIONS:
                try:
                    await db.execute(migration)
                    await db.commit()
                except Exception:
                    pass  # column may already exist

    async def save(self, job: AnalysisJob) -> None:
        async with self._connect() as db:
            await db.execute(
                """INSERT INTO analysis_jobs
                   (id, symbol, status, phase, progress, result_summary, error, created_at, started_at, completed_at, output_files, steps_json, config, retry_count, max_retries)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                   status=excluded.status,
                   phase=excluded.phase,
                   progress=excluded.progress,
                   result_summary=excluded.result_summary,
                   error=excluded.error,
                   started_at=excluded.started_at,
                   completed_at=excluded.completed_at,
                   output_files=excluded.output_files,
                   steps_json=excluded.steps_json,
                   config=excluded.config,
                   retry_count=excluded.retry_count,
                   max_retries=excluded.max_retries""",
                (
                    job.id,
                    job.symbol,
                    job.status.value,
                    job.phase,
                    job.progress,
                    job.result_summary,
                    job.error,
                    job.created_at.isoformat(),
                    job.started_at.isoformat() if job.started_at else None,
                    job.completed_at.isoformat() if job.completed_at else None,
                    json.dumps(job.output_files, default=str),
                    json.dumps([s.model_dump(mode="json") for s in job.steps], default=str),
                    json.dumps(job.config, default=str) if job.config else "{}",
                    job.retry_count,
                    job.max_retries,
                ),
            )
            await db.commit()

    async def claim_next_pending(self) -> Optional[AnalysisJob]:
        """Atomically mark the oldest pending job as running and return it.
        Failed jobs (ERROR) are NOT auto-retried; they must be manually restarted."""
        async with self._connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                async with db.execute(
                    "SELECT * FROM analysis_jobs WHERE status = ? ORDER BY created_at ASC LIMIT 1",
                    (JobStatus.PENDING.value,),
                ) as cursor:
                    row = await cursor.fetchone()
                if not row:
                    await db.commit()
                    return None

                job = self._row_to_job(row)
                job.start()
                await db.execute(
                    """UPDATE analysis_jobs
                       SET status = ?, started_at = ?, error = ?
                       WHERE id = ? AND status = ?""",
                    (
                        job.status.value,
                        job.started_at.isoformat() if job.started_at else None,
                        "",
                        job.id,
                        JobStatus.PENDING.value,
                    ),
                )
                await db.commit()
                return job
            except Exception:
                await db.rollback()
                raise

    async def get(self, job_id: str) -> Optional[AnalysisJob]:
        async with self._connect() as db:
            async with db.execute(
                "SELECT * FROM analysis_jobs WHERE id = ?", (job_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return self._row_to_job(row)

    async def list_jobs(
        self,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        summary_only: bool = False,
    ) -> list[AnalysisJob]:
        async with self._connect() as db:
            where_clauses: list[str] = []
            params: list = []
            if symbol:
                where_clauses.append("symbol = ?")
                params.append(symbol)
            if status:
                where_clauses.append("status = ?")
                params.append(status)
            if summary_only:
                sql = "SELECT id, symbol, status, progress, created_at FROM analysis_jobs"
            else:
                sql = "SELECT * FROM analysis_jobs"
            if where_clauses:
                sql += " WHERE " + " AND ".join(where_clauses)
            sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            async with db.execute(sql, params) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_job(r) for r in rows]

    async def get_output_files(self, job_id: str) -> list[str]:
        async with self._connect() as db:
            async with db.execute(
                "SELECT output_files FROM analysis_jobs WHERE id = ?", (job_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return []
                return json.loads(row[0]) if row[0] else []

    # ---- Feedback ----

    async def save_feedback(self, job_id: str, step_id: str, feedback_type: str, comment: str = "") -> None:
        async with self._connect() as db:
            await db.execute(
                """INSERT INTO analysis_step_feedback
                   (job_id, step_id, feedback_type, comment, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (job_id, step_id, feedback_type, comment, datetime.now().isoformat()),
            )
            await db.commit()

    async def get_feedback(self, job_id: str) -> list[dict]:
        async with self._connect() as db:
            async with db.execute(
                """SELECT step_id, feedback_type, comment, created_at
                   FROM analysis_step_feedback
                   WHERE job_id = ?
                   ORDER BY created_at ASC""",
                (job_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "step_id": r["step_id"],
                        "feedback_type": r["feedback_type"],
                        "comment": r["comment"],
                        "created_at": r["created_at"],
                    }
                    for r in rows
                ]

    async def reclaim_stale_jobs(self, stale_minutes: int = 30) -> list[str]:
        """Reset running jobs whose started_at is older than stale_minutes to pending."""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(minutes=stale_minutes)
        async with self._connect() as db:
            async with db.execute(
                """SELECT id FROM analysis_jobs
                   WHERE status = ? AND (started_at IS NULL OR started_at < ?)""",
                (JobStatus.RUNNING.value, cutoff.isoformat()),
            ) as cursor:
                rows = await cursor.fetchall()
            job_ids = [r["id"] for r in rows]
            if job_ids:
                placeholders = ",".join("?" * len(job_ids))
                await db.execute(
                    f"""UPDATE analysis_jobs
                        SET status = ?, started_at = NULL, error = ?
                        WHERE id IN ({placeholders})""",
                    (JobStatus.PENDING.value, "Worker died mid-run (auto-reclaimed)") + tuple(job_ids),
                )
                await db.commit()
            return job_ids

    async def get_feedback_summary(self, job_id: str) -> dict:
        async with self._connect() as db:
            async with db.execute(
                """SELECT feedback_type, COUNT(*) as cnt
                   FROM analysis_step_feedback
                   WHERE job_id = ?
                   GROUP BY feedback_type""",
                (job_id,),
            ) as cursor:
                rows = await cursor.fetchall()
                summary = {"upvotes": 0, "downvotes": 0}
                for r in rows:
                    if r["feedback_type"] == "upvote":
                        summary["upvotes"] = r["cnt"]
                    elif r["feedback_type"] == "downvote":
                        summary["downvotes"] = r["cnt"]
                return summary

    # ---- Scheduled tasks ----

    async def list_scheduled_tasks(self) -> list[dict]:
        async with self._connect() as db:
            async with db.execute(
                "SELECT id, name, description, enabled, cron, updated_at FROM scheduled_tasks ORDER BY id"
            ) as cursor:
                rows = await cursor.fetchall()
                return [
                    {
                        "id": r["id"],
                        "name": r["name"],
                        "description": r["description"],
                        "enabled": bool(r["enabled"]),
                        "cron": r["cron"],
                        "updated_at": r["updated_at"],
                    }
                    for r in rows
                ]

    async def get_scheduled_task(self, task_id: str) -> dict | None:
        async with self._connect() as db:
            async with db.execute(
                "SELECT id, name, description, enabled, cron, updated_at FROM scheduled_tasks WHERE id = ?",
                (task_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return {
                    "id": row["id"],
                    "name": row["name"],
                    "description": row["description"],
                    "enabled": bool(row["enabled"]),
                    "cron": row["cron"],
                    "updated_at": row["updated_at"],
                }

    async def save_scheduled_task(self, task: dict) -> None:
        async with self._connect() as db:
            await db.execute(
                """INSERT INTO scheduled_tasks
                   (id, name, description, enabled, cron, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                   enabled=excluded.enabled,
                   cron=excluded.cron,
                   updated_at=excluded.updated_at""",
                (
                    task["id"],
                    task.get("name", ""),
                    task.get("description", ""),
                    1 if task.get("enabled") else 0,
                    task.get("cron", ""),
                    datetime.now().isoformat(),
                ),
            )
            await db.commit()

    def _row_to_job(self, row: aiosqlite.Row) -> AnalysisJob:
        job = AnalysisJob(
            id=row["id"],
            symbol=row["symbol"],
        )
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        job.status = JobStatus(row["status"] if "status" in keys else JobStatus.PENDING.value)
        job.phase = row["phase"] if "phase" in keys and row["phase"] else ""
        job.progress = row["progress"] if "progress" in keys and row["progress"] else ""
        job.result_summary = row["result_summary"] if "result_summary" in keys and row["result_summary"] else ""
        job.error = row["error"] if "error" in keys and row["error"] else ""
        if "created_at" in keys and row["created_at"]:
            job.created_at = datetime.fromisoformat(row["created_at"])
        if "started_at" in keys and row["started_at"]:
            job.started_at = datetime.fromisoformat(row["started_at"])
        if "completed_at" in keys and row["completed_at"]:
            job.completed_at = datetime.fromisoformat(row["completed_at"])
        if "output_files" in keys and row["output_files"]:
            job.output_files = json.loads(row["output_files"])
        if "steps_json" in keys and row["steps_json"] and row["steps_json"] != "[]":
            steps_data = json.loads(row["steps_json"])
            job.steps = [AnalysisStep(**s) for s in steps_data]
        if "config" in keys and row["config"] and row["config"] != "{}":
            job.config = json.loads(row["config"])
        if "retry_count" in keys and row["retry_count"] is not None:
            job.retry_count = int(row["retry_count"])
        if "max_retries" in keys and row["max_retries"] is not None:
            job.max_retries = int(row["max_retries"])
        return job

