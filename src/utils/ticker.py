# src/utils/ticker.py
import re

# Tickers can contain letters, digits, dot, dash, underscore, and caret.
# Anything else is rejected before values are interpolated into paths.
_TICKER_PATH_RE = re.compile(r"^[A-Za-z0-9._\-\^]+$")


def detect_market(symbol: str) -> str:
    s = symbol.strip().upper()
    if "." in s:
        s = s.split(".")[0]
    if re.fullmatch(r"\d{6}", s):
        return "CN"
    if re.fullmatch(r"0\d{4}|1\d{4}|2\d{4}|3\d{4}|6\d{4}|8\d{4}", s):
        return "HK"
    return "US"


def normalize_ticker(symbol: str) -> str:
    s = symbol.strip().upper()
    known_suffixes = {".SH", ".SZ", ".SS", ".BJ"}
    for suffix in known_suffixes:
        if s.endswith(suffix):
            return s[: -len(suffix)]
    return s.replace(".", "-")


def safe_ticker_component(value: str, *, max_len: int = 32) -> str:
    """Validate ``value`` is safe to interpolate into a filesystem path."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"ticker must be a non-empty string, got {value!r}")
    if len(value) > max_len:
        raise ValueError(f"ticker exceeds {max_len} chars: {value!r}")
    if not _TICKER_PATH_RE.fullmatch(value):
        raise ValueError(
            f"ticker contains characters not allowed in a filesystem path: {value!r}"
        )
    if set(value) == {"."}:
        raise ValueError(f"ticker cannot consist solely of dots: {value!r}")
    return value
