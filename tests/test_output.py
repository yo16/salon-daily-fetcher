"""output.py のテスト: index累積マージ / 未取得選別 / md保存 / corpus再生成 / CSV。"""

import json
from pathlib import Path

from src.models import Article, ArticleMeta, IndexEntry
from src.output import (
    load_index, save_index, merge_listed, select_targets,
    save_article_md, upsert_index, rebuild_corpus, export_csv,
)


def _meta(i: str, date: str = "2026-06-02") -> ArticleMeta:
    return ArticleMeta(id=i, title=f"title-{i}", date=date, url=f"https://salon.jp/a/{i}")


def _article(i: str, date: str = "2026-06-02", body: str = "本文テキスト") -> Article:
    return Article(meta=_meta(i, date), body=body, fetched_at="2026-06-02T09:00:00+09:00")


# --- index 読み書き -----------------------------------------------------------
def test_load_index_missing_returns_empty(tmp_path):
    assert load_index(str(tmp_path / "index.json")) == {}


def test_save_then_load_index_roundtrip(tmp_path):
    path = str(tmp_path / "index.json")
    index = {"1": IndexEntry(id="1", title="t", date="2026-06-02",
                             url="https://salon.jp/a/1", listed_at="2026-06-02T00:00:00+09:00",
                             body_fetched=True, fetched_at="2026-06-02T09:00:00+09:00",
                             md_path="articles/2026-06-02/1.md")}
    save_index(index, path)
    assert Path(path).exists()
    loaded = load_index(path)
    assert loaded["1"].title == "t"
    assert loaded["1"].body_fetched is True
    assert loaded["1"].md_path == "articles/2026-06-02/1.md"


def test_index_json_has_schema_version(tmp_path):
    path = str(tmp_path / "index.json")
    save_index({}, path)
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert "updated_at" in raw and "articles" in raw


# --- merge_listed -------------------------------------------------------------
def test_merge_listed_adds_new_and_counts(tmp_path):
    index: dict = {}
    n = merge_listed(index, [_meta("1"), _meta("2")], now="2026-06-02T00:00:00+09:00")
    assert n == 2
    assert index["1"].body_fetched is False
    assert index["1"].listed_at == "2026-06-02T00:00:00+09:00"


def test_merge_listed_preserves_listed_at_and_fetched(tmp_path):
    index = {"1": IndexEntry(id="1", title="old", date="2026-06-01",
                             url="u", listed_at="2026-06-01T00:00:00+09:00",
                             body_fetched=True, fetched_at="2026-06-01T09:00:00+09:00",
                             md_path="articles/2026-06-01/1.md")}
    n = merge_listed(index, [_meta("1")], now="2026-06-02T00:00:00+09:00")
    assert n == 0  # 既存なので新規0
    assert index["1"].listed_at == "2026-06-01T00:00:00+09:00"  # 保持
    assert index["1"].body_fetched is True                       # 保持
    assert index["1"].title == "title-1"                          # 更新


# --- select_targets -----------------------------------------------------------
def test_select_targets_skips_fetched_and_keeps_order():
    listed = [_meta("3"), _meta("2"), _meta("1")]  # newest_first
    index = {"2": IndexEntry(id="2", title="t", date="2026-06-02", url="u",
                             listed_at="x", body_fetched=True)}
    targets = select_targets(listed, index, max_items=50)
    assert [m.id for m in targets] == ["3", "1"]  # 2はスキップ、順序維持


def test_select_targets_respects_max_items():
    listed = [_meta("3"), _meta("2"), _meta("1")]
    targets = select_targets(listed, {}, max_items=2)
    assert [m.id for m in targets] == ["3", "2"]


def test_select_targets_includes_listed_but_unfetched():
    listed = [_meta("1")]
    index = {"1": IndexEntry(id="1", title="t", date="2026-06-02", url="u",
                             listed_at="x", body_fetched=False)}
    assert [m.id for m in select_targets(listed, index, 50)] == ["1"]


# --- save_article_md + upsert_index ------------------------------------------
def test_save_article_md_writes_frontmatter_and_body(tmp_path):
    rel = save_article_md(_article("1", body="これは本文"), base_dir=str(tmp_path))
    assert rel == "articles/2026-06-02/1.md"
    text = (tmp_path / rel).read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "id: '1'" in text or 'id: "1"' in text or "id: 1" in text
    assert "これは本文" in text


def test_upsert_index_marks_fetched_and_keeps_listed_at():
    index = {"1": IndexEntry(id="1", title="t", date="2026-06-02", url="u",
                             listed_at="2026-06-01T00:00:00+09:00", body_fetched=False)}
    upsert_index(index, _article("1"), "articles/2026-06-02/1.md")
    assert index["1"].body_fetched is True
    assert index["1"].fetched_at == "2026-06-02T09:00:00+09:00"
    assert index["1"].md_path == "articles/2026-06-02/1.md"
    assert index["1"].listed_at == "2026-06-01T00:00:00+09:00"  # 保持


# --- rebuild_corpus -----------------------------------------------------------
def test_rebuild_corpus_one_line_per_fetched_no_dup(tmp_path):
    base = str(tmp_path)
    index: dict = {}
    for i in ("1", "2"):
        rel = save_article_md(_article(i, body=f"body-{i}"), base_dir=base)
        upsert_index(index, _article(i, body=f"body-{i}"), rel)
    # 未取得の記事は corpus に出ない
    merge_listed(index, [_meta("3")])
    n = rebuild_corpus(index, base_dir=base)
    assert n == 2
    lines = (tmp_path / "corpus.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    recs = [json.loads(ln) for ln in lines]
    ids = {r["id"] for r in recs}
    assert ids == {"1", "2"}
    assert any(r["body"] == "body-1" for r in recs)


def test_rebuild_corpus_is_idempotent(tmp_path):
    base = str(tmp_path)
    index: dict = {}
    rel = save_article_md(_article("1", body="b"), base_dir=base)
    upsert_index(index, _article("1", body="b"), rel)
    rebuild_corpus(index, base_dir=base)
    first = (tmp_path / "corpus.jsonl").read_text(encoding="utf-8")
    rebuild_corpus(index, base_dir=base)
    second = (tmp_path / "corpus.jsonl").read_text(encoding="utf-8")
    assert first == second  # 再生成しても重複・差分なし


# --- export_csv ---------------------------------------------------------------
def test_export_csv_header_and_rows(tmp_path):
    out = str(tmp_path / "index.csv")
    index = {"1": IndexEntry(id="1", title="タイトル", date="2026-06-02",
                             url="https://salon.jp/a/1", listed_at="x",
                             body_fetched=True, fetched_at="2026-06-02T09:00:00+09:00")}
    export_csv(index, out)
    text = Path(out).read_text(encoding="utf-8-sig")
    assert "id,title,date,url,body_fetched,fetched_at" in text
    assert "タイトル" in text
