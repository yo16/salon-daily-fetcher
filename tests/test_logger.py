"""logger.py のテスト: ロガー構成 / サマリ出力 / URL秘匿 / デバッグ成果物。"""

import logging
from pathlib import Path

from src.logger import setup_logger, step, redact_url, save_debug, write_summary
from src.models import RunSummary


def test_setup_logger_creates_dated_file_and_writes(tmp_path):
    logger = setup_logger(str(tmp_path))
    logger.info("hello-test")
    for h in logger.handlers:
        h.flush()
    files = list(tmp_path.glob("run-*.log"))
    assert len(files) == 1
    assert "hello-test" in files[0].read_text(encoding="utf-8")


def test_setup_logger_is_idempotent_no_duplicate_handlers(tmp_path):
    setup_logger(str(tmp_path))
    logger = setup_logger(str(tmp_path))
    # file + console の2つだけ（再呼び出しで重複しない）
    assert len(logger.handlers) == 2


def test_redact_url_strips_query_and_fragment():
    assert redact_url("https://salon.jp/a/1?token=secret#frag") == "https://salon.jp/a/1"
    assert redact_url("https://salon.jp/list") == "https://salon.jp/list"


def test_write_summary_logs_counts(tmp_path):
    logger = setup_logger(str(tmp_path))
    summary = RunSummary(
        started_at="2026-06-02T09:00:00",
        listed_count=20, new_count=3, skipped_count=17, failed_count=0,
        finished_at="2026-06-02T09:00:14", status="success",
    )
    write_summary(summary, logger)
    for h in logging.getLogger("salon").handlers:
        h.flush()
    text = list(tmp_path.glob("run-*.log"))[0].read_text(encoding="utf-8")
    assert "listed=20" in text
    assert "new=3" in text
    assert "status=success" in text
    assert "elapsed=14.0s" in text


class _FakePage:
    def __init__(self, html: str):
        self._html = html
        self.shot_path = None

    def screenshot(self, path: str, full_page: bool = False):
        Path(path).write_bytes(b"PNGDATA")
        self.shot_path = path

    def content(self) -> str:
        return self._html


def test_save_debug_writes_screenshot_and_html(tmp_path):
    page = _FakePage("<html>x</html>")
    debug_dir = save_debug(page, log_dir=str(tmp_path))
    d = Path(debug_dir)
    assert (d / "screenshot.png").exists()
    assert (d / "page.html").read_text(encoding="utf-8") == "<html>x</html>"


def test_save_debug_swallows_page_errors(tmp_path):
    class _Broken:
        def screenshot(self, path, full_page=False):
            raise RuntimeError("boom")

        def content(self):
            raise RuntimeError("boom")

    # 例外を投げず、ディレクトリパスを返す
    debug_dir = save_debug(_Broken(), log_dir=str(tmp_path))
    assert Path(debug_dir).exists()
