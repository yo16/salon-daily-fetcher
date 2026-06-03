"""textutil.py のテスト: ID採番 / 日付正規化 / 本文整形 / リトライ。

（fetch.py の Playwright 操作は実サイト/ブラウザが必要なため、ここでは純粋ロジックを検証する。）
"""

from datetime import date

import pytest

from src.textutil import (
    derive_id, normalize_date, clean_text, with_retry,
    article_id_from_src, hash_id,
)


# --- derive_id ----------------------------------------------------------------
def test_derive_id_last_segment():
    assert derive_id("https://salon.jp/a/12345") == "12345"


def test_derive_id_trailing_slash():
    assert derive_id("https://salon.jp/a/12345/") == "12345"


def test_derive_id_keeps_safe_slug():
    assert derive_id("https://salon.jp/a/post-1_2") == "post-1_2"


def test_derive_id_query_is_ignored():
    assert derive_id("https://salon.jp/a/77?ref=x") == "77"


def test_derive_id_unsafe_segment_falls_back_to_hash():
    rid = derive_id("https://salon.jp/a/記事タイトル")
    assert len(rid) == 12
    assert all(c in "0123456789abcdef" for c in rid)


def test_derive_id_is_stable():
    url = "https://salon.jp/a/記事タイトル"
    assert derive_id(url) == derive_id(url)


def test_derive_id_no_segment_falls_back_to_hash():
    assert len(derive_id("https://salon.jp/")) == 12


# --- normalize_date -----------------------------------------------------------
def test_normalize_date_japanese():
    assert normalize_date("2026年6月2日") == "2026-06-02"


def test_normalize_date_slash():
    assert normalize_date("2026/06/02") == "2026-06-02"


def test_normalize_date_iso_passthrough():
    assert normalize_date("2026-06-02") == "2026-06-02"


def test_normalize_date_month_day_uses_today_year():
    assert normalize_date("6月2日", today=date(2026, 6, 30)) == "2026-06-02"


def test_normalize_date_today_keyword():
    assert normalize_date("本日", today=date(2026, 6, 2)) == "2026-06-02"


def test_normalize_date_yesterday_keyword():
    assert normalize_date("昨日", today=date(2026, 6, 2)) == "2026-06-01"


def test_normalize_date_relative_hours_is_today():
    assert normalize_date("19時間前", today=date(2026, 6, 3)) == "2026-06-03"


def test_normalize_date_relative_minutes_is_today():
    assert normalize_date("5分前", today=date(2026, 6, 3)) == "2026-06-03"


def test_normalize_date_relative_days_ago():
    assert normalize_date("3日前", today=date(2026, 6, 3)) == "2026-05-31"


def test_normalize_date_relative_weeks_ago():
    assert normalize_date("2週間前", today=date(2026, 6, 3)) == "2026-05-20"


def test_normalize_date_day_before_yesterday():
    assert normalize_date("一昨日", today=date(2026, 6, 3)) == "2026-06-01"


def test_normalize_date_invalid_raises():
    with pytest.raises(ValueError):
        normalize_date("日付不明")


# --- article_id_from_src / hash_id -------------------------------------------
def test_article_id_from_src_thumbnail():
    src = "/thumbnails/show/articles/9Mc391al0FO/320"
    assert article_id_from_src(src) == "9Mc391al0FO"


def test_article_id_from_src_none_or_unmatched():
    assert article_id_from_src(None) is None
    assert article_id_from_src("/user_icons/get/abc") is None


def test_hash_id_stable_and_length():
    assert hash_id("本文テキスト") == hash_id("本文テキスト")
    assert len(hash_id("x")) == 12
    assert hash_id("a") != hash_id("b")


def test_normalize_date_invalid_calendar_raises():
    with pytest.raises(ValueError):
        normalize_date("2026-13-40")


# --- clean_text ---------------------------------------------------------------
def test_clean_text_collapses_blank_lines_and_trims():
    raw = "  行1  \n\n\n\n行2\n\n"
    assert clean_text(raw) == "行1\n\n行2"


def test_clean_text_empty():
    assert clean_text("") == ""
    assert clean_text(None) == ""


def test_clean_text_crlf_normalized():
    assert clean_text("a\r\nb") == "a\nb"


# --- with_retry ---------------------------------------------------------------
def test_with_retry_succeeds_after_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    assert with_retry(flaky, attempts=3, backoff=0) == "ok"
    assert calls["n"] == 3


def test_with_retry_raises_after_exhaustion():
    def always_fail():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        with_retry(always_fail, attempts=2, backoff=0)


def test_with_retry_only_catches_specified_exceptions():
    def raises_key():
        raise KeyError("x")

    with pytest.raises(KeyError):
        with_retry(raises_key, attempts=3, backoff=0, exc=(ValueError,))
