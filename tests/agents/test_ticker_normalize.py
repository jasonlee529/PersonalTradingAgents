import pytest
from src.utils.ticker import normalize_ticker


@pytest.mark.parametrize(
    "input,expected",
    [
        ("600519.SH", "600519"),
        ("000001.SZ", "000001"),
        ("835305.BJ", "835305"),
        ("600519.SS", "600519"),
        ("sh600519", "SH600519"),  # prefix not stripped by normalize_ticker
        ("AAPL", "AAPL"),
        ("BRK.B", "BRK-B"),
    ],
)
def test_normalize_ticker(input, expected):
    assert normalize_ticker(input) == expected
