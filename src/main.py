"""エントリポイント: 全体フローのオーケストレーション・多重起動防止・終了コード。

設計: docs/design.md §3, §5.6, §8.3, §10
実行: python -m src.main

終了コード:
  0 成功（部分成功含む。詳細は RunSummary.status）
  1 想定外の致命的エラー
  2 設定 / 認証エラー（ConfigError）
  3 ログイン失敗（LoginError）
  4 多重起動（LockError）
"""

import os
import time
from datetime import date, datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from . import output
from .config import load_config, load_credentials
from .fetch import extract_list, fetch_body
from .logger import redact_url, save_debug, setup_logger, step, write_summary
from .models import (
    AppError, Article, ConfigError, ExtractionError, LockError, LoginError,
    RunSummary,
)
from .session import ensure_logged_in, new_context

LOCK_PATH = "data/.lock"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# --- 多重起動防止（design §10）-----------------------------------------------
def acquire_lock(path: str, stale_minutes: int, logger) -> None:
    """ロックを取得する。既存ロックが新しければ LockError、stale なら奪取する。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        age_min = (time.time() - p.stat().st_mtime) / 60
        if age_min < stale_minutes:
            raise LockError(f"既に実行中です（ロック: {path}, 経過 {age_min:.1f}分）")
        if logger is not None:
            logger.warning(f"stale ロックを奪取します（経過 {age_min:.1f}分）")
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    try:
        fd = os.open(str(p), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as e:  # チェックと作成の間の競合
        raise LockError(f"既に実行中です（ロック: {path}）") from e
    with os.fdopen(fd, "w") as f:
        f.write(f"{os.getpid()} {_now()}")


def release_lock(path: str) -> None:
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass


# --- 本体 --------------------------------------------------------------------
def main() -> int:
    logger = setup_logger()
    summary = RunSummary(started_at=_now())
    cfg = None
    page = None
    lock_acquired = False
    try:
        try:
            cfg = load_config()
            creds = load_credentials()
        except ConfigError as e:
            logger.error(f"設定エラー: {e}")
            summary.status = "failed"
            return 2

        try:
            acquire_lock(LOCK_PATH, cfg.lock_stale_minutes, logger)
            lock_acquired = True
        except LockError as e:
            logger.error(str(e))
            summary.status = "failed"
            return 4

        index = output.load_index()
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=cfg.headless)
            try:
                context = new_context(browser, cfg)
                page = context.new_page()
                page.set_default_timeout(cfg.timeout_ms)

                ensure_logged_in(page, cfg, creds, logger=step("login"))

                today = date.today()
                listed = extract_list(page, cfg, today=today, logger=step("extract_list"))
                summary.listed_count = len(listed)
                new_in_list = output.merge_listed(index, listed)
                targets = output.select_targets(listed, index, cfg.max_items_per_run)
                step("extract_list").info(
                    f"listed={len(listed)} new_in_list={new_in_list} targets={len(targets)}"
                )
                if len(targets) >= cfg.max_items_per_run:
                    step("extract_list").info(
                        f"上限 {cfg.max_items_per_run} 件で打ち切り（未処理が残る場合は次回継続）"
                    )

                lg = step("fetch_body")
                for meta in targets:
                    try:
                        body = fetch_body(page, cfg, meta.url, logger=lg)
                        article = Article(meta=meta, body=body, fetched_at=_now())
                        md_path = output.save_article_md(article)
                        output.upsert_index(index, article, md_path)
                        summary.new_count += 1
                        lg.info(f"saved {meta.id} ({redact_url(meta.url)})")
                    except ExtractionError as e:
                        summary.failed_count += 1
                        lg.error(f"記事取得失敗 {meta.id}: {e}")
                        if cfg.on_element_missing == "abort":
                            raise
                    time.sleep(cfg.throttle_seconds)

                summary.skipped_count = max(
                    0, summary.listed_count - summary.new_count - summary.failed_count
                )
                output.save_index(index)
                output.rebuild_corpus(index)
                if cfg.output_csv:
                    output.export_csv(index)
            finally:
                browser.close()

        if summary.failed_count > 0:
            summary.status = "partial"
        return 0

    except LoginError as e:
        logger.error(f"ログイン失敗: {e}")
        _maybe_debug(cfg, page)
        summary.status = "failed"
        return 3
    except AppError as e:
        logger.error(f"処理エラー: {e}")
        _maybe_debug(cfg, page)
        summary.status = "failed"
        return 1
    except Exception as e:  # 想定外
        logger.exception(f"想定外のエラー: {e}")
        _maybe_debug(cfg, page)
        summary.status = "failed"
        return 1
    finally:
        summary.finished_at = _now()
        write_summary(summary, logger)
        if lock_acquired:
            release_lock(LOCK_PATH)


def _maybe_debug(cfg, page) -> None:
    if cfg is not None and getattr(cfg, "save_debug_on_error", False) and page is not None:
        try:
            save_debug(page)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
