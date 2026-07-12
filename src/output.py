"""出力・永続化: index.json / 本文Markdown / corpus.jsonl / CSV。

設計: docs/design.md §4.2, §5.4, §6.3, §6.4, §8.5
- index.json は id をキーに累積マージ（履歴保持）。
- save_index は temp→os.replace のアトミック書込（データを壊さない）。
- corpus.jsonl は毎回 index + md から再生成（1記事1行・重複なし）。
"""

import csv
import json
import os
import shutil
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
            exported_at=rec.get("exported_at"),
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


# --- newsletter 取込先への受け渡し（export）-----------------------------------
def _archive_exported(entry: IndexEntry, base: Path, archived_subdir: str) -> None:
    """ローカル md を data/<archived_subdir>/<date>/<id>.md へ移動し md_path を更新する。

    data/articles に取得物を無条件に残さないための「処理済み」退避。
    - 元ファイルがあれば移動（同一ドライブ内アトミック）して md_path を更新。
    - 既に退避済み（元無し・退避先あり）なら md_path の更新のみ。
    - どちらも無ければ md_path は変更しない（実体が失われている）。
    """
    if not entry.md_path:
        return
    archived_rel = f"{archived_subdir}/{entry.date}/{entry.id}.md"
    src = base / entry.md_path
    archived = base / archived_rel
    if src.exists():
        archived.parent.mkdir(parents=True, exist_ok=True)
        os.replace(src, archived)
        entry.md_path = archived_rel
    elif archived.exists():
        entry.md_path = archived_rel


def export_pending(index: dict[str, IndexEntry], export_dir: str,
                   data_dir: str = "data", archived_subdir: str = "exported",
                   now: str | None = None, logger=None) -> int:
    """未受渡し(exported_at=None)の本文を newsletter 取込先へ受け渡す。戻り値: 受渡し件数。

    各記事を export_dir/<date>/<id>.md へコピー（取込先の inbox）し、ローカル md は
    data/<archived_subdir>/ へ移動して二重送信を防ぐ。index は exported_at と
    （移動後の）md_path を更新する。コピー→移動→index更新の途中で中断しても、
    次回は「退避済み・index未更新」を検出して整合を取り戻す（自己修復）。
    """
    now = now or _now_iso()
    base = Path(data_dir)
    dest_root = Path(export_dir)
    count = 0
    for entry in _sorted_entries(index):
        if not entry.body_fetched or entry.exported_at or not entry.md_path:
            continue
        src = base / entry.md_path
        archived = base / f"{archived_subdir}/{entry.date}/{entry.id}.md"
        if src.exists():
            dest = dest_root / f"{entry.date}/{entry.id}.md"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            _archive_exported(entry, base, archived_subdir)
            entry.exported_at = now
            count += 1
            if logger is not None:
                logger.info(f"exported {entry.id} -> {dest}")
        elif archived.exists():
            # 前回 移動済みだが index 未更新だった場合の復旧（取込先へは配信済み前提）。
            entry.md_path = f"{archived_subdir}/{entry.date}/{entry.id}.md"
            entry.exported_at = now
            if logger is not None:
                logger.info(f"reconciled {entry.id} (already archived)")
        # 元・退避先ともに無い場合は実体が失われているためスキップ（未受渡しのまま）。
    return count


def mark_all_exported(index: dict[str, IndexEntry], data_dir: str = "data",
                      archived_subdir: str = "exported", now: str | None = None) -> int:
    """既に取込先へ渡し済みの全 body_fetched 記事を export 済みにする一回限りのバックフィル。

    取込先へのコピーは行わず、ローカル md のみ data/<archived_subdir> へ退避して
    exported_at を付与する。戻り値: マークした件数。
    """
    now = now or _now_iso()
    base = Path(data_dir)
    count = 0
    for entry in _sorted_entries(index):
        if not entry.body_fetched or entry.exported_at:
            continue
        _archive_exported(entry, base, archived_subdir)
        entry.exported_at = now
        count += 1
    return count


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
