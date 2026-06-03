"""ログ・実行サマリ・失敗時デバッグ成果物。

設計: docs/design.md §8.4, §9
- 出力: logs/run-YYYY-MM-DD.log（日次ファイル）＋ コンソール。
- フォーマット: 時刻 | レベル | ステップ名 | メッセージ。
- 認証情報はログに出さない（呼び出し側の規律）。URL はクエリを除去して記録する。
"""

import logging
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from .models import RunSummary

LOGGER_NAME = "salon"
_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logger(log_dir: str = "logs", debug: bool = False) -> logging.Logger:
    """ファイル（日次）＋コンソールの2ハンドラを持つロガーを構成して返す。

    再呼び出ししてもハンドラは重複しない（既存をクリアする）。
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    fmt = logging.Formatter(_FORMAT, datefmt=_DATEFMT)
    date_str = datetime.now().strftime("%Y-%m-%d")
    file_handler = logging.FileHandler(
        Path(log_dir) / f"run-{date_str}.log", encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    # Windows コンソール(cp932)での日本語文字化けを防ぐため UTF-8 を強制する
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def step(name: str) -> logging.Logger:
    """ステップ名付きの子ロガーを返す（ログのステップ列に表示される）。"""
    return logging.getLogger(f"{LOGGER_NAME}.{name}")


def redact_url(url: str) -> str:
    """URL からクエリ・フラグメントを除去（トークン混入を防ぐ）。"""
    try:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except Exception:
        return url


def save_debug(page, log_dir: str = "logs") -> str:
    """失敗時にスクリーンショットとページHTMLを保存し、保存先ディレクトリを返す。

    デバッグ保存自体の失敗は握りつぶす（元のエラーを覆い隠さないため）。
    """
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    debug_dir = Path(log_dir) / "debug" / ts
    debug_dir.mkdir(parents=True, exist_ok=True)
    try:
        page.screenshot(path=str(debug_dir / "screenshot.png"), full_page=True)
    except Exception:
        pass
    try:
        (debug_dir / "page.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    return str(debug_dir)


def write_summary(summary: RunSummary, logger: logging.Logger) -> None:
    """実行サマリを1行でログ出力する。"""
    s = summary
    elapsed = ""
    if s.finished_at:
        try:
            dt0 = datetime.fromisoformat(s.started_at)
            dt1 = datetime.fromisoformat(s.finished_at)
            elapsed = f" elapsed={(dt1 - dt0).total_seconds():.1f}s"
        except ValueError:
            elapsed = ""
    msg = (
        f"listed={s.listed_count} new={s.new_count} skipped={s.skipped_count} "
        f"failed={s.failed_count} status={s.status}{elapsed}"
    )
    step("summary").info(msg)
