"""サイト非依存の純粋ユーティリティ（ID採番・日付正規化・本文整形・リトライ）。

Playwright に依存しないため単体テストが容易。fetch.py から利用する。
設計: docs/design.md §6.1, §6.2, §8.2
"""

import hashlib
import re
import time
from datetime import date, timedelta
from urllib.parse import urlsplit

_SAFE_RE = re.compile(r"[^A-Za-z0-9_-]")
_FULL_DATE_RE = re.compile(r"(\d{4})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2})")
_MD_DATE_RE = re.compile(r"(\d{1,2})\D{1,3}(\d{1,2})")


def derive_id(url: str) -> str:
    """記事URLから安定IDを採番する（design §6.1）。

    既定: URL末尾の非空パスセグメント。安全([A-Za-z0-9_-])でない場合は
    URL全体の SHA1 先頭12桁にフォールバックする。
    """
    seg = ""
    for part in urlsplit(url).path.split("/"):
        if part:
            seg = part
    if seg and not _SAFE_RE.search(seg):
        return seg
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def normalize_date(raw: str, today: date | None = None) -> str:
    """日付表記を ISO 'YYYY-MM-DD' に正規化する（design §6.2）。

    解析できない場合は ValueError。年が無い表記は today の年で補完する。
    """
    if today is None:
        today = date.today()
    if raw is None:
        raise ValueError("date is None")
    s = raw.strip()
    if any(k in s for k in ("今日", "本日")):
        return today.isoformat()
    if "昨日" in s:
        return (today - timedelta(days=1)).isoformat()
    m = _FULL_DATE_RE.search(s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    m = _MD_DATE_RE.search(s)
    if m:
        return date(today.year, int(m.group(1)), int(m.group(2))).isoformat()
    raise ValueError(f"cannot parse date: {raw!r}")


def clean_text(text: str) -> str:
    """本文テキストを整形する（行末空白除去・連続空行の圧縮・前後トリム）。"""
    if not text:
        return ""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    out: list[str] = []
    blank = 0
    for line in normalized.split("\n"):
        line = line.rstrip()
        if line == "":
            blank += 1
            if blank <= 1:
                out.append("")
        else:
            blank = 0
            out.append(line)
    return "\n".join(out).strip()


def with_retry(fn, attempts: int = 3, backoff: float = 2.0,
               logger=None, label: str = "", exc: tuple = (Exception,)):
    """fn() を最大 attempts 回、指数バックオフで試行する（design §8.2）。

    全失敗時は最後の例外を送出する。
    """
    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except exc as e:  # noqa: PERF203
            last = e
            if logger is not None:
                logger.warning(f"{label}: retry {attempt}/{attempts} ({type(e).__name__}: {e})")
            if attempt < attempts:
                time.sleep(backoff * (2 ** (attempt - 1)))
    assert last is not None
    raise last
