# src/utils/logger.py
import contextvars
from contextlib import contextmanager
import inspect
import logging
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from src.config import settings

LOG_FMT = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(class_name)s | "
    "trace=%(trace_id)s | job=%(job_id)s | symbol=%(symbol)s | %(message)s"
)

_trace_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
_job_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("job_id", default=None)
_symbol_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("symbol", default=None)
_rate_limit_lock = threading.Lock()
_rate_limit_state: dict[str, dict[str, float | int]] = {}


def set_trace_id(trace_id: str | None) -> None:
    """Set the current request trace id for logging context."""
    _trace_id_var.set(trace_id)


def get_trace_id() -> str | None:
    """Get the current request trace id from logging context."""
    return _trace_id_var.get()


def set_job_context(job_id: str | None = None, symbol: str | None = None) -> None:
    """Set background job context for log correlation."""
    _job_id_var.set(job_id)
    _symbol_var.set(symbol)


def get_job_context() -> tuple[str | None, str | None]:
    """Get the current background job context."""
    return _job_id_var.get(), _symbol_var.get()


@contextmanager
def logging_context(
    *,
    trace_id: str | None = None,
    job_id: str | None = None,
    symbol: str | None = None,
):
    """Temporarily attach trace/job context to logs in this execution context."""
    trace_token = _trace_id_var.set(trace_id) if trace_id is not None else None
    job_token = _job_id_var.set(job_id) if job_id is not None else None
    symbol_token = _symbol_var.set(symbol) if symbol is not None else None
    try:
        yield
    finally:
        if symbol_token is not None:
            _symbol_var.reset(symbol_token)
        if job_token is not None:
            _job_id_var.reset(job_token)
        if trace_token is not None:
            _trace_id_var.reset(trace_token)


def _get_caller_class_name() -> str:
    """Traverse the call stack to find the class name of the logging caller."""
    frame = inspect.currentframe()
    if frame is None:
        return "-"
    try:
        # Walk up the stack: _get_caller_class_name -> filter -> logging internals -> caller
        f = frame.f_back  # filter
        depth = 0
        while f and depth < 12:
            code = f.f_code
            # Skip logging internals and this module
            if "logging" not in code.co_filename and code.co_filename != __file__:
                # Check for instance method call (self) or classmethod (cls)
                if "self" in f.f_locals:
                    return f.f_locals["self"].__class__.__name__
                if "cls" in f.f_locals:
                    return f.f_locals["cls"].__name__
            f = f.f_back
            depth += 1
        return "-"
    finally:
        del frame


class ContextFilter(logging.Filter):
    """Inject contextual fields into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id_var.get() or "-"
        record.job_id = _job_id_var.get() or "-"
        record.symbol = _symbol_var.get() or "-"
        record.class_name = _get_caller_class_name()
        return True


def _cleanup_old_logs(log_dir: Path, retention_days: int) -> None:
    """Delete log files in *log_dir* older than *retention_days*."""
    if retention_days <= 0:
        return
    cutoff = time.time() - retention_days * 86400
    for path in log_dir.iterdir():
        if path.is_file() and path.stat().st_mtime < cutoff:
            try:
                path.unlink()
            except OSError:
                pass


def rate_limited_warning(
    logger: logging.Logger,
    key: str,
    message: str,
    *args,
    interval_seconds: float = 60.0,
    summary_every: int = 10,
) -> None:
    """Log the first warning immediately and summarize repeats within the interval."""
    now = time.monotonic()
    with _rate_limit_lock:
        state = _rate_limit_state.setdefault(key, {"last": 0.0, "suppressed": 0})
        last = float(state["last"])
        suppressed = int(state["suppressed"])
        if now - last >= interval_seconds:
            if suppressed:
                logger.warning(
                    "Suppressed %d repeated warnings for %s since last emission",
                    suppressed,
                    key,
                )
            state["last"] = now
            state["suppressed"] = 0
            logger.warning(message, *args)
            return

        suppressed += 1
        state["suppressed"] = suppressed
        if summary_every > 0 and suppressed % summary_every == 0:
            logger.warning(
                "Suppressed %d repeated warnings for %s; latest: %s",
                suppressed,
                key,
                message % args if args else message,
            )
        else:
            logger.debug(message, *args)


def setup_logging(
    level: int = logging.INFO,
    log_dir: Path = Path("./data/logs"),
    log_name: str = "backend.log",
    retention_days: int | None = None,
    console: bool = True,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> Path:
    """Configure root logger with both console and file output.

    Returns the path to the log file.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    _configure_stdio_encoding()
    _cleanup_old_logs(
        log_dir,
        settings.log_retention_days if retention_days is None else retention_days,
    )

    log_file = log_dir / log_name

    formatter = logging.Formatter(LOG_FMT)
    context_filter = ContextFilter()

    handlers: list[logging.Handler] = []
    if console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.addFilter(context_filter)
        handlers.append(console_handler)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(context_filter)
    handlers.append(file_handler)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    for handler in handlers:
        root.addHandler(handler)

    return log_file


def _configure_stdio_encoding() -> None:
    """Make console logging tolerant of non-UTF-8 Windows streams."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


def get_recent_logs(log_file: Path, lines: int = 200) -> str:
    """Return the last N lines of the log file."""
    if not log_file.exists():
        return "Log file not found."
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            all_lines = f.readlines()
            return "".join(all_lines[-lines:])
    except Exception as e:
        return f"Error reading logs: {e}"
