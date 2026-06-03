"""fetch.extract_articles のテスト（Fake DOM で投稿者フィルタ・インライン抽出・ID採番を検証）。

実ブラウザは使わず、Playwright の要素APIを模した Fake で挙動を確認する。
"""

from datetime import date

from src.fetch import extract_articles
from src.models import Config, RetryPolicy, Selectors


class FakeNode:
    def __init__(self, text="", attrs=None, html=""):
        self._text = text
        self._attrs = attrs or {}
        self._html = html

    def inner_text(self):
        return self._text

    def text_content(self):
        return self._text

    def inner_html(self):
        return self._html

    def get_attribute(self, name):
        return self._attrs.get(name)


class FakeItem:
    def __init__(self, mapping):
        self._m = mapping

    def query_selector(self, sel):
        return self._m.get(sel)


class FakePage:
    def __init__(self, items):
        self._items = items

    def goto(self, url, timeout=None):
        pass

    def wait_for_selector(self, sel, timeout=None):
        return True

    def query_selector_all(self, sel):
        return self._items


def _config(author_filter="西野亮廣エンタメ研究所") -> Config:
    return Config(
        login_url="https://salon.jp/authentications/login_individual",
        list_url="https://salon.jp/nishino",
        selectors=Selectors(
            login_email="x", login_password="y", login_submit="z",
            logged_in_mark="#js-timeline-container",
            list_item=".item", item_author=".user-name",
            item_title=".timeline-header-message", item_date=".posted",
            body=".timeline-body-text", item_image=".timeline-body-image",
        ),
        author_filter=author_filter,
        retry=RetryPolicy(max_attempts=1, backoff_seconds=0),
        timeout_ms=1000,
    )


def _target_item():
    return FakeItem({
        ".user-name": FakeNode("西野亮廣エンタメ研究所"),
        ".timeline-header-message": FakeNode("第2ラウンドの準備が進む"),
        ".posted": FakeNode("19時間前"),
        ".timeline-body-text": FakeNode("  本文1\n\n\n本文2  "),
        ".timeline-body-image": FakeNode(attrs={"src": "/thumbnails/show/articles/9Mc391al0FO/320"}),
    })


def _other_item():
    return FakeItem({
        ".user-name": FakeNode("おすすめユーザー"),
        ".timeline-header-message": FakeNode("広告"),
        ".posted": FakeNode("1日前"),
        ".timeline-body-text": FakeNode("別の投稿者の本文"),
    })


def test_extract_filters_by_author_and_parses_fields():
    page = FakePage([_target_item(), _other_item()])
    arts = extract_articles(page, _config(), today=date(2026, 6, 3))
    assert len(arts) == 1                       # 対象投稿者のみ
    a = arts[0]
    assert a.meta.id == "9Mc391al0FO"           # 画像srcから記事ID
    assert a.meta.title == "第2ラウンドの準備が進む"
    assert a.meta.date == "2026-06-03"          # 「19時間前」→当日
    assert a.body == "本文1\n\n本文2"            # clean_text 済み
    assert a.meta.url == "https://salon.jp/nishino#9Mc391al0FO"


def test_extract_without_author_filter_returns_all():
    page = FakePage([_target_item(), _other_item()])
    arts = extract_articles(page, _config(author_filter=""), today=date(2026, 6, 3))
    assert len(arts) == 2


def test_extract_id_falls_back_to_body_hash_when_no_image():
    item = FakeItem({
        ".user-name": FakeNode("西野亮廣エンタメ研究所"),
        ".timeline-header-message": FakeNode("画像なし投稿"),
        ".posted": FakeNode("3日前"),
        ".timeline-body-text": FakeNode("ハッシュ対象の本文"),
        # item_image 無し
    })
    arts = extract_articles(FakePage([item]), _config(), today=date(2026, 6, 3))
    assert len(arts) == 1
    assert len(arts[0].meta.id) == 12           # 本文ハッシュ(12桁)
    assert arts[0].meta.date == "2026-05-31"    # 「3日前」
