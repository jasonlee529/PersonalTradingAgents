"""Notification routing configuration."""

from typing import Dict, List, Optional, Tuple

ROUTABLE_CHANNELS = frozenset(["wechat", "feishu", "email"])

ROUTE_CONFIGS: Dict[str, Dict[str, str]] = {
    "report": {
        "config_attr": "notification_report_channels",
        "description": "Routes daily report notifications.",
    },
    "alert": {
        "config_attr": "notification_alert_channels",
        "description": "Routes event-driven alert notifications.",
    },
    "system_error": {
        "config_attr": "notification_system_error_channels",
        "description": "Routes system error notifications.",
    },
}


def parse_channels(raw_value: object) -> List[str]:
    """Parse comma-separated channel strings."""
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        items = raw_value.split(",")
    elif isinstance(raw_value, (list, tuple, set)):
        items = raw_value
    else:
        items = [raw_value]

    channels: List[str] = []
    for item in items:
        token = str(item).strip().lower()
        if token:
            channels.append(token)
    return channels


def split_channels(channels: List[str]) -> Tuple[List[str], List[str]]:
    """Return valid and invalid channel names."""
    valid: List[str] = []
    invalid: List[str] = []
    seen = set()

    for ch in parse_channels(channels):
        if ch in ROUTABLE_CHANNELS:
            if ch not in seen:
                valid.append(ch)
                seen.add(ch)
        elif ch not in seen:
            invalid.append(ch)
            seen.add(ch)
    return valid, invalid


def get_route_config(route_type: Optional[str]) -> Optional[Dict[str, str]]:
    if route_type is None:
        return None
    return ROUTE_CONFIGS.get(str(route_type).strip().lower())
