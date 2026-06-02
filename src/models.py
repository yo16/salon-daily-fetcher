"""共有データ型と例外定義（純データ＋例外。ロジックは持たない）。

設計: docs/design.md §4.1（dataclass）, §8.1（例外階層）
"""

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 例外階層（design §8.1）
#   AppError を基底とし、main.py が種別ごとに終了コードへマッピングする。
# ---------------------------------------------------------------------------
class AppError(Exception):
    """本アプリの基底例外。"""


class ConfigError(AppError):
    """設定 / 認証情報の不備（→ 終了コード 2）。"""


class LockError(AppError):
    """多重起動（ロック取得失敗、→ 終了コード 4）。"""


class LoginError(AppError):
    """ログイン / セッション復元の最終失敗（→ 終了コード 3）。"""


class ExtractionError(AppError):
    """一覧 / 本文の抽出失敗（on_element_missing=abort 時に致命化）。"""


# ---------------------------------------------------------------------------
# 設定・認証（design §4.1）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Credentials:
    """認証情報（.env.local 由来）。ログ出力してはならない。"""

    email: str
    password: str


@dataclass(frozen=True)
class Selectors:
    """サイト構造に依存する CSS セレクタ群（config.yaml 由来）。"""

    login_email: str
    login_password: str
    login_submit: str
    logged_in_mark: str
    list_item: str
    item_link: str
    item_title: str
    item_date: str
    body: str
    noise: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RetryPolicy:
    """リトライ方針（design §8.2）。"""

    max_attempts: int = 3
    backoff_seconds: float = 2.0


@dataclass(frozen=True)
class Config:
    """アプリ全体の動作設定（config.yaml 由来）。"""

    login_url: str
    list_url: str
    selectors: Selectors
    headless: bool = True
    timeout_ms: int = 15000
    throttle_seconds: float = 2.0
    max_items_per_run: int = 50
    order: str = "newest_first"
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    on_login_failure: str = "abort"      # abort | continue
    on_element_missing: str = "skip"     # skip | abort
    save_debug_on_error: bool = True
    output_csv: bool = False
    body_as_markdown: bool = False
    lock_stale_minutes: int = 60


# ---------------------------------------------------------------------------
# 記事データ（design §4.1）
# ---------------------------------------------------------------------------
@dataclass
class ArticleMeta:
    """一覧から抽出した記事のメタ情報。"""

    id: str            # 安定ID（URL末尾セグメント由来。design §6.1）
    title: str
    date: str          # ISO 'YYYY-MM-DD' に正規化済み（design §6.2）
    url: str           # 絶対URL


@dataclass
class Article:
    """本文まで取得した記事。"""

    meta: ArticleMeta
    body: str          # クリーンテキスト本文
    fetched_at: str    # ISO8601 取得時刻


@dataclass
class IndexEntry:
    """index.json の1レコード（取得管理マスタ）。"""

    id: str
    title: str
    date: str
    url: str
    listed_at: str               # 一覧で最初に観測した時刻
    body_fetched: bool = False
    fetched_at: str | None = None
    md_path: str | None = None   # data/ からの相対パス


@dataclass
class RunSummary:
    """1回の実行結果サマリ（ログ末尾に出力）。"""

    started_at: str
    listed_count: int = 0
    new_count: int = 0           # 今回新規取得した本文件数
    skipped_count: int = 0       # 既取得でスキップ
    failed_count: int = 0
    finished_at: str | None = None
    status: str = "success"      # success | partial | failed
