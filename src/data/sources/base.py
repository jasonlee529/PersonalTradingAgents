from abc import ABC, abstractmethod
from typing import Optional


class DataSource(ABC):
    """Abstract base for all data sources."""

    name: str = ""

    # ---- Core data ----
    @abstractmethod
    async def get_quote(self, symbol: str) -> Optional[dict]:
        """Latest price/volume/change."""
        ...

    @abstractmethod
    async def get_kline(
        self, symbol: str, period: str = "1d", limit: int = 60
    ) -> Optional[list[dict]]:
        """OHLCV history."""
        ...

    @abstractmethod
    async def get_fundamentals(self, symbol: str) -> Optional[dict]:
        """Key fundamental metrics (PE, PB, etc)."""
        ...

    # ---- Financial statements ----
    async def get_balance_sheet(
        self, symbol: str, freq: str = "quarterly"
    ) -> Optional[list[dict]]:
        """Balance sheet data. Override if supported."""
        return None

    async def get_cashflow(
        self, symbol: str, freq: str = "quarterly"
    ) -> Optional[list[dict]]:
        """Cash flow statement. Override if supported."""
        return None

    async def get_income_statement(
        self, symbol: str, freq: str = "quarterly"
    ) -> Optional[list[dict]]:
        """Income statement. Override if supported."""
        return None

    # ---- News ----
    async def get_news(
        self, symbol: str, start_date: str = "", end_date: str = "", limit: int = 20
    ) -> Optional[list[dict]]:
        """Stock-specific news. Override if supported."""
        return None

    async def get_global_news(
        self, look_back_days: int = 7, limit: int = 10
    ) -> Optional[list[dict]]:
        """Global market news. Override if supported."""
        return None

    # ---- Local market signals ----
    async def fetch_consensus_expectations(self, symbol: str) -> Optional[dict]:
        """Consensus EPS forecast. Override if supported."""
        return None

    async def fetch_market_heatmap(self, date: str = "") -> Optional[list[dict]]:
        """Hot stocks with topic attribution. Override if supported."""
        return None

    async def fetch_cross_border_flow(
        self, include_history: bool = False
    ) -> Optional[dict]:
        """Northbound capital flow. Override if supported."""
        return None

    async def fetch_theme_exposure(self, symbol: str) -> Optional[list[dict]]:
        """Concept/sector blocks. Override if supported."""
        return None

    async def fetch_order_flow_profile(
        self, symbol: str, include_history: bool = True
    ) -> Optional[dict]:
        """Individual stock fund flow. Override if supported."""
        return None

    async def fetch_trading_seat_activity(
        self, symbol: str, trade_date: str = "", look_back_days: int = 30
    ) -> Optional[dict]:
        """Dragon-tiger board appearances. Override if supported."""
        return None

    async def fetch_supply_unlock_schedule(
        self, symbol: str, trade_date: str = "", forward_days: int = 90
    ) -> Optional[list[dict]]:
        """Lockup expiry calendar. Override if supported."""
        return None

    async def fetch_peer_industry_snapshot(
        self, symbol: str, top_n: int = 20
    ) -> Optional[list[dict]]:
        """Industry sector performance comparison. Override if supported."""
        return None

    # ---- Market overview ----
    async def get_market_indices(self) -> Optional[list[dict]]:
        """Major index quotes (SSE, SZSE, ChiNext, etc). Override if supported."""
        return None

    async def get_market_statistics(self) -> Optional[dict]:
        """Market breadth stats: up/down/flat count, limit-up/down, turnover. Override if supported."""
        return None

    async def get_limit_up_stocks(
        self, trade_date: str = "", market: str = "all"
    ) -> Optional[list[dict]]:
        """Daily limit-up stock pool. Override if supported."""
        return None

    async def get_sector_rankings(self, n: int = 5) -> Optional[tuple[list[dict], list[dict]]]:
        """Top and bottom performing sectors. Override if supported."""
        return None

    async def health_check(self) -> bool:
        return True

