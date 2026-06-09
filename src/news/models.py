from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class NewsItem(BaseModel):
    title: str
    content: str = ""
    source: str
    published_at: str
    url: str = ""
    relevance_score: float = 0.0
    concepts: list[str] = []


class Announcement(BaseModel):
    title: str
    type: str = ""
    published_at: str
    url: str = ""
    relevance_score: float = 1.0  # Direct company announcement = always relevant


class ResearchReport(BaseModel):
    title: str
    institution: str = ""
    rating: str = ""
    target_price: str = ""
    published_at: str
    url: str = ""
    relevance_score: float = 1.0
    predict_this_year_eps: Optional[str] = None
    predict_next_year_eps: Optional[str] = None
