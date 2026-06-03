"""モジュール横断の純粋パイプライン結合テスト（サイト非依存）。

実サイト/Playwright を使わず、一覧メタ → index マージ → 未取得選別 → md保存 →
index更新 → 保存 → corpus再生成 の流れを「2回の実行」として再現し、
当日→過去への遡及・冪等性・重複なしを検証する。
"""

import json
from pathlib import Path

from src.models import Article, ArticleMeta
from src.output import (
    load_index, save_index, merge_listed, select_targets,
    save_article_md, upsert_index, rebuild_corpus,
)


def _meta(i: str, date: str = "2026-06-02") -> ArticleMeta:
    return ArticleMeta(id=i, title=f"記事{i}", date=date, url=f"https://salon.jp/a/{i}")


def _fetch_and_store(index, meta, base_dir):
    """1記事の「本文取得→保存→index更新」を模す。"""
    article = Article(meta=meta, body=f"本文-{meta.id}", fetched_at="2026-06-02T09:00:00+09:00")
    md_path = save_article_md(article, base_dir=base_dir)
    upsert_index(index, article, md_path)


def test_two_run_backfill_and_idempotency(tmp_path):
    base = str(tmp_path)
    index_path = str(tmp_path / "index.json")

    # === 1回目の実行 ===
    listed_run1 = [_meta("3"), _meta("2"), _meta("1")]  # newest_first
    index = load_index(index_path)
    assert index == {}
    assert merge_listed(index, listed_run1) == 3          # 一覧3件すべて新規

    targets1 = select_targets(listed_run1, index, max_items=2)  # 上限2 → 当日側2件
    assert [m.id for m in targets1] == ["3", "2"]
    for m in targets1:
        _fetch_and_store(index, m, base)
    save_index(index, index_path)
    assert rebuild_corpus(index, base_dir=base) == 2

    # === 2回目の実行（同じ一覧 + 新着a4）===
    index = load_index(index_path)                         # 永続化から復元
    assert index["3"].body_fetched is True
    assert index["1"].body_fetched is False                # 1回目は上限で未取得

    listed_run2 = [_meta("4"), _meta("3"), _meta("2"), _meta("1")]
    assert merge_listed(index, listed_run2) == 1           # a4 のみ新規

    targets2 = select_targets(listed_run2, index, max_items=50)
    # 既取得(3,2)はスキップ、未取得(4 と 過去に遡った 1)が対象
    assert [m.id for m in targets2] == ["4", "1"]
    for m in targets2:
        _fetch_and_store(index, m, base)
    save_index(index, index_path)
    n = rebuild_corpus(index, base_dir=base)

    # 全4件が1記事1行・重複なし
    assert n == 4
    lines = (tmp_path / "corpus.jsonl").read_text(encoding="utf-8").strip().splitlines()
    recs = [json.loads(ln) for ln in lines]
    assert sorted(r["id"] for r in recs) == ["1", "2", "3", "4"]
    assert len({r["id"] for r in recs}) == 4                # 重複なし

    # === 3回目（新着なし）→ 取得対象ゼロ、結果不変 ===
    index = load_index(index_path)
    assert merge_listed(index, listed_run2) == 0
    assert select_targets(listed_run2, index, max_items=50) == []
    before = (tmp_path / "corpus.jsonl").read_text(encoding="utf-8")
    rebuild_corpus(index, base_dir=base)
    after = (tmp_path / "corpus.jsonl").read_text(encoding="utf-8")
    assert before == after                                  # 冪等


def test_listed_at_preserved_across_runs(tmp_path):
    index_path = str(tmp_path / "index.json")
    index = {}
    merge_listed(index, [_meta("1")], now="2026-06-01T00:00:00+09:00")
    save_index(index, index_path)

    index = load_index(index_path)
    # 後日の実行で再観測しても listed_at は最初の値を保持
    merge_listed(index, [_meta("1")], now="2026-06-05T00:00:00+09:00")
    assert index["1"].listed_at == "2026-06-01T00:00:00+09:00"
