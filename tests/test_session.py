"""session.py のテスト: storage state の分岐 / 復元成功 / 失効時の再ログイン。

Playwright の実ブラウザは使わず、Fake オブジェクトで分岐ロジックを検証する。
"""

from pathlib import Path

from playwright.sync_api import Error as PWError

import src.session as session
from src.session import new_context, save_state, ensure_logged_in
from src.models import Config, Credentials, Selectors


def _config() -> Config:
    return Config(
        login_url="https://salon.jp/login",
        list_url="https://salon.jp/list",
        selectors=Selectors(
            login_email="a", login_password="b", login_submit="c",
            logged_in_mark=".mark", list_item="e", item_author="f",
            item_title="g", item_date="h", body="i",
        ),
        timeout_ms=3000,
    )


class FakeContext:
    def __init__(self):
        self.saved_to = None

    def storage_state(self, path):
        Path(path).write_text("{}", encoding="utf-8")
        self.saved_to = path


class FakeBrowser:
    def __init__(self):
        self.kwargs = None

    def new_context(self, **kwargs):
        self.kwargs = kwargs
        return FakeContext()


class FakePage:
    def __init__(self, logged_in, context):
        self._logged_in = logged_in
        self.context = context
        self.goto_url = None

    def goto(self, url, timeout=None):
        self.goto_url = url

    def wait_for_selector(self, selector, timeout=None):
        if self._logged_in:
            return object()
        raise PWError("not visible")


def test_new_context_without_state(tmp_path):
    b = FakeBrowser()
    new_context(b, _config(), session_path=str(tmp_path / "state.json"))
    assert "storage_state" not in b.kwargs


def test_new_context_with_state(tmp_path):
    sp = tmp_path / "state.json"
    sp.write_text("{}", encoding="utf-8")
    b = FakeBrowser()
    new_context(b, _config(), session_path=str(sp))
    assert b.kwargs.get("storage_state") == str(sp)


def test_save_state_creates_file_and_dir(tmp_path):
    ctx = FakeContext()
    sp = str(tmp_path / "session" / "state.json")
    save_state(ctx, sp)
    assert Path(sp).exists()
    assert ctx.saved_to == sp


def test_ensure_logged_in_uses_restored_session(tmp_path, monkeypatch):
    called = {"login": 0}
    monkeypatch.setattr(session, "login", lambda *a, **k: called.__setitem__("login", called["login"] + 1))
    page = FakePage(logged_in=True, context=FakeContext())
    ok = ensure_logged_in(page, _config(), Credentials("e@x", "p"),
                          session_path=str(tmp_path / "st.json"))
    assert ok is True
    assert called["login"] == 0          # 復元成功 → ログイン不要
    assert page.goto_url == "https://salon.jp/list"


def test_ensure_logged_in_relogins_when_expired(tmp_path, monkeypatch):
    called = {"login": 0}
    monkeypatch.setattr(session, "login", lambda *a, **k: called.__setitem__("login", called["login"] + 1))
    sp = str(tmp_path / "st.json")
    page = FakePage(logged_in=False, context=FakeContext())
    ok = ensure_logged_in(page, _config(), Credentials("e@x", "p"), session_path=sp)
    assert ok is True
    assert called["login"] == 1          # 失効 → 再ログイン
    assert Path(sp).exists()             # state 保存
