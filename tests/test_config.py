from src.config import Settings


def test_settings_exposes_news_limits_defaults():
    settings = Settings()

    assert settings.news_article_limit == 20
    assert settings.global_news_article_limit == 10
    assert settings.global_news_lookback_days == 7
