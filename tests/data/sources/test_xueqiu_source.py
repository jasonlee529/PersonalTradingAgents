from types import SimpleNamespace

import pytest

from src.data.sources.xueqiu_source import XueqiuSource


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = payload or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeCookies(dict):
    def set(self, name, value, domain=None, path=None):
        self[name] = value


class FakeSession:
    def __init__(self, payload=None, fail=False):
        self.cookies = FakeCookies()
        self.payload = payload or {}
        self.fail = fail
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers, timeout))
        if self.fail:
            raise RuntimeError("boom")
        return FakeResponse(self.payload)


@pytest.mark.asyncio
async def test_xueqiu_uses_configured_cookie_without_auto_lookup():
    source = XueqiuSource(
        SimpleNamespace(
            xueqiu_cookie="xq_a_token=abc; u=123",
            xueqiu_auto_cookie=False,
            xueqiu_timeout=1,
        )
    )
    source._session = FakeSession(
        payload={
            "list": [
                {
                    "title": "Test post",
                    "text": "<p>hello</p>",
                    "created_at": 1_700_000_000_000,
                    "user": {"screen_name": "tester"},
                    "target": "/123/456",
                }
            ]
        }
    )

    result = await source.get_news("600519")

    assert result[0]["title"] == "Test post"
    assert result[0]["source"] == "xueqiu:tester"
    assert source._session.cookies["xq_a_token"] == "abc"


@pytest.mark.asyncio
async def test_xueqiu_failure_returns_none_for_collector_fallback():
    source = XueqiuSource(
        SimpleNamespace(xueqiu_cookie="xq_a_token=abc", xueqiu_auto_cookie=False, xueqiu_timeout=1)
    )
    source._session = FakeSession(fail=True)

    result = await source.get_news("600519")

    assert result is None


def test_xueqiu_auto_cookie_loads_from_browser(monkeypatch):
    source = XueqiuSource(
        SimpleNamespace(xueqiu_cookie="", xueqiu_auto_cookie=True, xueqiu_timeout=1)
    )

    def load_browser_cookie():
        source._session.cookies.set("xq_a_token", "browser-token")
        return True

    source._load_cookies_from_browser = load_browser_cookie
    source._load_homepage_cookies = lambda: False

    assert source._ensure_cookies() is True
    assert source._session.cookies["xq_a_token"] == "browser-token"


def test_xueqiu_browser_cookie_is_persisted(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("EXISTING=1\n", encoding="utf-8")
    source = XueqiuSource(
        SimpleNamespace(
            xueqiu_cookie="",
            xueqiu_auto_cookie=True,
            xueqiu_timeout=1,
            settings_env_path=env_path,
        )
    )
    source._session.cookies.set("xq_a_token", "browser-token", domain=".xueqiu.com", path="/")
    source._session.cookies.set("u", "123", domain=".xueqiu.com", path="/")

    source._persist_cookie_string()

    text = env_path.read_text(encoding="utf-8")
    assert "EXISTING=1" in text
    assert "XUEQIU_COOKIE=xq_a_token=browser-token; u=123" in text
