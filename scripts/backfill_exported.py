"""一回限りのバックフィル: 既存の取得済み記事を export 済みとしてマークする。

背景:
  export 機能（newsletter 取込先への受け渡し）を導入する以前に取得した記事は、
  既に手動 / 旧 run.bat 経由で newsletter 側へ取込済み（import/imported/ に存在）だが、
  index.json には exported_at が無い。このまま新フローを動かすと「未受渡し」とみなされ
  全件が再コピー→再import され、取込処理が一度だけ空回りする。

このスクリプトは index.json の全 body_fetched 記事に exported_at を付与し、
ローカル md を data/exported/ へ退避する（取込先へのコピーは行わない）。
冪等: 2 回目以降はマーク対象が無く 0 件で終わる。

実行: python scripts/backfill_exported.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.output import load_index, mark_all_exported, save_index  # noqa: E402


def main() -> int:
    index = load_index()
    if not index:
        print("index.json が空、または存在しません。対象なし。")
        return 0
    pending = sum(1 for e in index.values() if e.body_fetched and not e.exported_at)
    n = mark_all_exported(index)
    save_index(index)
    print(f"backfill 完了: {n} 件を export 済みにマーク（未受渡しだった {pending} 件）。")
    print("ローカル md は data/exported/ へ退避しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
