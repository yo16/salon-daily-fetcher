"""models.py のテスト: dataclass の既定値・不変性、例外階層を検証する。"""

import dataclasses

import pytest

from src.models import (
    AppError, ConfigError, LockError, LoginError, ExtractionError,
    Credentials, Selectors, RetryPolicy, Config, ArticleMeta, Article,
    IndexEntry, RunSummary,
)


def _selectors() -> Selectors:
    return Selectors(
        login_email="a", login_password="b", login_submit="c",
        logged_in_mark="d", list_item="e", item_author="f",
        item_title="g", item_date="h", body="i",
    )


def test_exception_hierarchy():
    for exc in (ConfigError, LockError, LoginError, ExtractionError):
        assert issubclass(exc, AppError)
    assert issubclass(AppError, Exception)


def test_config_defaults():
    cfg = Config(login_url="u", list_url="v", selectors=_selectors())
    assert cfg.headless is True
    assert cfg.timeout_ms == 15000
    assert cfg.max_items_per_run == 50
    assert cfg.order == "newest_first"
    assert isinstance(cfg.retry, RetryPolicy)
    assert cfg.retry.max_attempts == 3
    assert cfg.on_login_failure == "abort"
    assert cfg.on_element_missing == "skip"


def test_selectors_noise_default_is_independent():
    s1 = _selectors()
    s2 = _selectors()
    assert s1.noise == []
    assert s1.noise is not s2.noise  # default_factory により別インスタンス


def test_frozen_config_is_immutable():
    cfg = Config(login_url="u", list_url="v", selectors=_selectors())
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.headless = False  # type: ignore[misc]


def test_credentials_is_frozen():
    cred = Credentials(email="x@example.com", password="secret")
    with pytest.raises(dataclasses.FrozenInstanceError):
        cred.password = "changed"  # type: ignore[misc]


def test_index_entry_defaults():
    e = IndexEntry(
        id="1", title="t", date="2026-06-02", url="u",
        listed_at="2026-06-02T00:00:00+09:00",
    )
    assert e.body_fetched is False
    assert e.fetched_at is None
    assert e.md_path is None


def test_run_summary_defaults():
    s = RunSummary(started_at="2026-06-02T00:00:00+09:00")
    assert s.status == "success"
    assert s.new_count == 0
    assert s.failed_count == 0


def test_article_composition():
    meta = ArticleMeta(id="1", title="t", date="2026-06-02", url="u")
    art = Article(meta=meta, body="本文", fetched_at="2026-06-02T09:00:00+09:00")
    assert art.meta.id == "1"
    assert art.body == "本文"
