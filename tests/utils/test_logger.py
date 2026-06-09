import logging

from src.utils.logger import logging_context, rate_limited_warning, setup_logging


def test_setup_logging_supports_custom_log_name(temp_dir):
    log_file = setup_logging(
        level=logging.INFO,
        log_dir=temp_dir / "logs",
        log_name="worker.log",
        retention_days=0,
    )

    logging.getLogger("tests.logger").info("hello")

    assert log_file.name == "worker.log"
    assert log_file.exists()
    assert "hello" in log_file.read_text(encoding="utf-8")


def test_logging_context_writes_trace_job_and_symbol(temp_dir):
    log_file = setup_logging(
        level=logging.INFO,
        log_dir=temp_dir / "logs",
        log_name="context.log",
        retention_days=0,
        console=False,
    )

    with logging_context(trace_id="trace-1", job_id="job-1", symbol="600519"):
        logging.getLogger("tests.logger").info("context message")

    content = log_file.read_text(encoding="utf-8")
    assert "trace=trace-1" in content
    assert "job=job-1" in content
    assert "symbol=600519" in content
    assert "request_url" not in content


def test_rate_limited_warning_summarizes_repeats(caplog):
    logger = logging.getLogger("tests.rate_limit")
    caplog.set_level(logging.DEBUG, logger="tests.rate_limit")

    for i in range(3):
        rate_limited_warning(
            logger,
            "tests.rate_limit.key",
            "source failed %s",
            i,
            interval_seconds=60,
            summary_every=2,
        )

    warning_messages = [
        record.getMessage()
        for record in caplog.records
        if record.levelno == logging.WARNING
    ]
    assert "source failed 0" in warning_messages
    assert any("Suppressed 2 repeated warnings" in msg for msg in warning_messages)
