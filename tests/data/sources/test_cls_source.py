import pytest

from src.data.sources.cls_source import CLSSource


class FakeResponse:
    def __init__(self, text="", status_code=200, payload=None):
        self.text = text
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


@pytest.mark.asyncio
async def test_cls_global_news_empty_body(monkeypatch):
    monkeypatch.setattr(
        "src.data.sources.cls_source.requests.get",
        lambda *args, **kwargs: FakeResponse(text=""),
    )

    result = await CLSSource().get_global_news()
    assert result is None


@pytest.mark.asyncio
async def test_cls_global_news_non_json(monkeypatch):
    monkeypatch.setattr(
        "src.data.sources.cls_source.requests.get",
        lambda *args, **kwargs: FakeResponse(text="<html>blocked</html>"),
    )

    result = await CLSSource().get_global_news()
    assert result is None


@pytest.mark.asyncio
async def test_cls_global_news_success(monkeypatch):
    monkeypatch.setattr(
        "src.data.sources.cls_source.requests.get",
        lambda *args, **kwargs: FakeResponse(
            text='{"ok":true}',
            payload={
                "data": {
                    "roll_data": [
                        {
                            "title": "headline",
                            "brief": "brief",
                            "ctime": "1780300800",
                        }
                    ]
                }
            },
        ),
    )

    result = await CLSSource().get_global_news()
    assert result[0]["title"] == "headline"
    assert result[0]["source"] == "CLS Wire"
