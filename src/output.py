"""出力・永続化: index.json / 本文Markdown / corpus.jsonl / CSV。

設計: docs/design.md §4.2, §5.4, §6.3, §6.4, §8.5
- index.json は id をキーに累積マージ（履歴保持）。
- save_index は temp→os.replace のアトミック書込（データを壊さない）。
- corpus.jsonl は毎回 index + md から再生成（1記事1行・重複なし）。
"""

import csv
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import yaml

from .models import AppError, Article, ArticleMeta, IndexEntry


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _sorted_entries(index: dict[str, IndexEntry]) -> list[IndexEntry]:
    """決定的な順序（日付→id）で列挙する。"""
    return sorted(index.values(), key=lambda e: (e.date, e.id))


def _extract_md_body(text: str) -> str:
    """フロントマター付き Markdown から本文部分のみを取り出す。"""
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return "\n".join(lines[i + 1:]).lstrip("\n")
    return text


# --- index.json --------------------------------------------------------------
def load_index(path: str = "data/index.json") -> dict[str, IndexEntry]:
    """index.json を読み込む。無ければ空 dict。破損時は AppError。"""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise AppError(f"index.json の解析に失敗しました（破損の可能性）: {path}: {e}") from e
    articles = raw.get("articles", {}) if isinstance(raw, dict) else {}
    index: dict[str, IndexEntry] = {}
    for aid, rec in articles.items():
        index[aid] = IndexEntry(
            id=rec.get("id", aid),
            title=rec.get("title", ""),
            date=rec.get("date", ""),
            url=rec.get("url", ""),
            listed_at=rec.get("listed_at", ""),
            body_fetched=bool(rec.get("body_fetched", False)),
            fetched_at=rec.get("fetched_at"),
            md_path=rec.get("md_path"),
        )
    return index


def save_index(index: dict[str, IndexEntry], path: str = "data/index.json",
               now: str | None = None) -> None:
    """index.json をアトミックに保存（temp→os.replace）。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "updated_at": now or _now_iso(),
        "articles": {aid: asdict(entry) for aid, entry in index.items()},
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def merge_listed(index: dict[str, IndexEntry], listed: list[ArticleMeta],
                 now: str | None = None) -> int:
    """一覧で観測した記事メタを index にマージ（FR-07）。

    新規は body_fetched=False で追加。既存は title/date/url を更新しつつ
    listed_at / body_fetched / fetched_at / md_path は保持する。
    戻り値: 新規追加件数。
    """
    now = now or _now_iso()
    new_count = 0
    for meta in listed:
        existing = index.get(meta.id)
        if existing is None:
            index[meta.id] = IndexEntry(
                id=meta.id, title=meta.title, date=meta.date, url=meta.url,
                listed_at=now, body_fetched=False, fetched_at=None, md_path=None,
            )
            new_count += 1
        else:
            existing.title = meta.title
            existing.date = meta.date
            existing.url = meta.url
    return new_count


def select_targets(listed: list[ArticleMeta], index: dict[str, IndexEntry],
                   max_items: int) -> list[ArticleMeta]:
    """未取得(index未登録 or body_fetched=False)を、与えられた順序のまま最大 max_items 件選ぶ。

    listed は newest_first 前提（design §6.3）。
    """
    targets: list[ArticleMeta] = []
    for meta in listed:
        entry = index.get(meta.id)
        if entry is None or not entry.body_fetched:
            targets.append(meta)
        if len(targets) >= max_items:
            break
    return targets


# --- 本文 Markdown ------------------------------------------------------------
def save_article_md(article: Article, base_dir: str = "data") -> str:
    """本文を data/articles/<date>/<id>.md に保存し、base_dir からの相対パスを返す。"""
    meta = article.meta
    rel = f"articles/{meta.date}/{meta.id}.md"
    p = Path(base_dir) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    front = {
        "id": meta.id, "title": meta.title, "date": meta.date,
        "url": meta.url, "fetched_at": article.fetched_at,
    }
    fm = yaml.safe_dump(front, allow_unicode=True, sort_keys=False).strip()
    p.write_text(f"---\n{fm}\n---\n\n{article.body}\n", encoding="utf-8")
    return rel


def upsert_index(index: dict[str, IndexEntry], article: Article, md_path: str) -> None:
    """本文取得後の index 更新。listed_at は既存維持、body_fetched=True 等を設定。"""
    meta = article.meta
    entry = index.get(meta.id)
    if entry is None:
        entry = IndexEntry(
            id=meta.id, title=meta.title, date=meta.date, url=meta.url,
            listed_at=article.fetched_at,
        )
        index[meta.id] = entry
    entry.title = meta.title
    entry.date = meta.date
    entry.url = meta.url
    entry.body_fetched = True
    entry.fetched_at = article.fetched_at
    entry.md_path = md_path


# --- 派生成果物 ---------------------------------------------------------------
def rebuild_corpus(index: dict[str, IndexEntry], base_dir: str = "data") -> int:
    """index + 保存済み md から corpus.jsonl を再生成（1記事1行・重複なし）。戻り値: 行数。"""
    base = Path(base_dir)
    out = base / "corpus.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for entry in _sorted_entries(index):
        if not entry.body_fetched or not entry.md_path:
            continue
        md = base / entry.md_path
        if not md.exists():
            continue
        body = _extract_md_body(md.read_text(encoding="utf-8"))
        rec = {
            "id": entry.id, "title": entry.title, "date": entry.date,
            "url": entry.url, "body": body,
        }
        lines.append(json.dumps(rec, ensure_ascii=False))
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    os.replace(tmp, out)
    return len(lines)


def export_csv(index: dict[str, IndexEntry], out: str = "data/index.csv") -> None:
    """index を CSV 出力（Excel 閲覧用、UTF-8 BOM）。本文は含めない。"""
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "title", "date", "url", "body_fetched", "fetched_at"])
        for entry in _sorted_entries(index):
            writer.writerow([
                entry.id, entry.title, entry.date, entry.url,
                entry.body_fetched, entry.fetched_at or "",
            ])
