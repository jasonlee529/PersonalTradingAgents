# tests/portfolio/test_models.py
from decimal import Decimal
from src.portfolio.models import Holding, Position


def test_holding_creation():
    h = Holding(symbol="600519", name="贵州茅台", market="CN")
    assert h.symbol == "600519"
    assert h.market == "CN"


def test_position_update_price():
    p = Position(symbol="600519", quantity=100, avg_cost=Decimal("1500.00"))
    p.update_price(Decimal("1600.00"))
    assert p.current_price == Decimal("1600.00")
    assert p.market_value == Decimal("160000.00")
    assert p.unrealized_pnl == Decimal("10000.00")


def test_position_zero_quantity():
    p = Position(symbol="AAPL", quantity=0, avg_cost=Decimal("0"))
    p.update_price(Decimal("180.00"))
    assert p.unrealized_pnl is None
