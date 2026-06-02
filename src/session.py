"""セッション管理: storage state の保存・復元とログイン状態判定。

設計: docs/design.md §5.2, §7
- 保存済みセッションを優先利用し、失効時のみ .env.local の資格情報で再ログイン。
- 失効検知は logged_in_mark の有無のみで軽量に判定する。
"""

from pathlib import Path

from playwright.sync_api import Error as PWError

from .fetch import login
from .models import Config, Credentials

SESSION_PATH = "session/state.json"
_CHECK_TIMEOUT_MS = 5000  # ログイン状態チェックは短めに（未ログイン時に待ち過ぎない）


def new_context(browser, config: Config, session_path: str = SESSION_PATH):
    """storage state があれば適用して context を生成、無ければ素で生成する。"""
    p = Path(session_path)
    if p.exists():
        return browser.new_context(storage_state=str(p))
    return browser.new_context()


def save_state(context, session_path: str = SESSION_PATH) -> None:
    """context の storage state を保存する（ディレクトリは自動作成）。"""
    p = Path(session_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(p))


def _is_logged_in(page, mark: str, timeout_ms: int) -> bool:
    check = min(timeout_ms, _CHECK_TIMEOUT_MS)
    try:
        page.wait_for_selector(mark, timeout=check)
        return True
    except PWError:
        return False


def ensure_logged_in(page, config: Config, creds: Credentials,
                     logger=None, session_path: str = SESSION_PATH) -> bool:
    """ログイン状態を保証する。

    list_url を開いて logged_in_mark を確認し、未ログインなら login() を実行して
    storage state を保存する。最終的にログインできなければ LoginError（login が送出）。
    """
    page.goto(config.list_url, timeout=config.timeout_ms)
    if _is_logged_in(page, config.selectors.logged_in_mark, config.timeout_ms):
        if logger is not None:
            logger.info("session restored, skip login")
        return True

    if logger is not None:
        logger.info("session absent or expired; logging in")
    login(page, config, creds, logger=logger)  # 失敗時 LoginError
    save_state(page.context, session_path)
    if logger is not None:
        logger.info("login succeeded; session saved")
    return True
