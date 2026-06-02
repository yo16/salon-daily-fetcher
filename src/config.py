"""設定 (config.yaml) と認証情報 (.env.local) の読込・検証。

設計: docs/design.md §5.1, §12
- ネットワーク処理の前に全検証を行い、設定ミスを早期に弾く。
- プレースホルダ '<...>' が残っている場合は「未設定」とみなし ConfigError。
- 認証情報の値はログ出力しない。
"""

import re
from pathlib import Path

import yaml
from dotenv import dotenv_values

from .models import Config, Credentials, RetryPolicy, Selectors, ConfigError

_PLACEHOLDER_RE = re.compile(r"<[^>]*>")

_SELECTOR_KEYS = (
    "login_email", "login_password", "login_submit", "logged_in_mark",
    "list_item", "item_link", "item_title", "item_date", "body",
)


# --- 検証ヘルパ ---------------------------------------------------------------
def _require(mapping: dict, key: str, ctx: str):
    if key not in mapping or mapping[key] is None:
        raise ConfigError(f"{ctx}: 必須キー '{key}' がありません")
    return mapping[key]


def _as_str(value, ctx: str) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise ConfigError(f"{ctx}: 非空の文字列が必要です (値: {value!r})")
    return value


def _no_placeholder(value: str, ctx: str) -> str:
    if _PLACEHOLDER_RE.search(value):
        raise ConfigError(
            f"{ctx}: プレースホルダ '<...>' が未設定です (値: {value!r})。実値に置き換えてください"
        )
    return value


def _as_url(value, ctx: str) -> str:
    v = _as_str(value, ctx)
    _no_placeholder(v, ctx)
    if not (v.startswith("http://") or v.startswith("https://")):
        raise ConfigError(f"{ctx}: http(s) URL が必要です (値: {value!r})")
    return v


def _as_bool(value, ctx: str, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise ConfigError(f"{ctx}: 真偽値が必要です (値: {value!r})")
    return value


def _as_int(value, ctx: str, lo: int, hi: int, default: int) -> int:
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{ctx}: 整数が必要です (値: {value!r})")
    if not (lo <= value <= hi):
        raise ConfigError(f"{ctx}: {lo}〜{hi} の範囲が必要です (値: {value})")
    return value


def _as_number(value, ctx: str, lo: float, hi: float, default: float) -> float:
    if value is None:
        value = default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{ctx}: 数値が必要です (値: {value!r})")
    if not (lo <= value <= hi):
        raise ConfigError(f"{ctx}: {lo}〜{hi} の範囲が必要です (値: {value})")
    return float(value)


def _as_choice(value, ctx: str, choices: tuple[str, ...], default: str) -> str:
    if value is None:
        value = default
    if value not in choices:
        raise ConfigError(f"{ctx}: {list(choices)} のいずれかが必要です (値: {value!r})")
    return value


# --- 公開API -----------------------------------------------------------------
def load_config(path: str = "config.yaml") -> Config:
    """config.yaml を読み込み、検証済みの Config を返す。

    検証失敗時は ConfigError を送出する（design §12）。
    """
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"設定ファイルがありません: {path}")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"config.yaml のYAML解析に失敗しました: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError("config.yaml はマッピング(キー: 値)である必要があります")

    login_url = _as_url(_require(data, "login_url", "config"), "login_url")
    list_url = _as_url(_require(data, "list_url", "config"), "list_url")

    sel_raw = _require(data, "selectors", "config")
    if not isinstance(sel_raw, dict):
        raise ConfigError("selectors はマッピングである必要があります")
    sel_values = {}
    for key in _SELECTOR_KEYS:
        v = _as_str(_require(sel_raw, key, "selectors"), f"selectors.{key}")
        sel_values[key] = _no_placeholder(v, f"selectors.{key}")
    noise = sel_raw.get("noise") or []
    if not isinstance(noise, list) or not all(isinstance(x, str) for x in noise):
        raise ConfigError("selectors.noise は文字列のリストである必要があります")
    selectors = Selectors(noise=list(noise), **sel_values)

    retry_raw = data.get("retry") or {}
    if not isinstance(retry_raw, dict):
        raise ConfigError("retry はマッピングである必要があります")
    retry = RetryPolicy(
        max_attempts=_as_int(retry_raw.get("max_attempts"), "retry.max_attempts", 1, 10, default=3),
        backoff_seconds=_as_number(retry_raw.get("backoff_seconds"), "retry.backoff_seconds", 0, 30, default=2),
    )

    return Config(
        login_url=login_url,
        list_url=list_url,
        selectors=selectors,
        headless=_as_bool(data.get("headless"), "headless", default=True),
        timeout_ms=_as_int(data.get("timeout_ms"), "timeout_ms", 1000, 120000, default=15000),
        throttle_seconds=_as_number(data.get("throttle_seconds"), "throttle_seconds", 0, 60, default=2),
        max_items_per_run=_as_int(data.get("max_items_per_run"), "max_items_per_run", 1, 500, default=50),
        order=_as_choice(data.get("order"), "order", ("newest_first",), default="newest_first"),
        retry=retry,
        on_login_failure=_as_choice(data.get("on_login_failure"), "on_login_failure", ("abort", "continue"), default="abort"),
        on_element_missing=_as_choice(data.get("on_element_missing"), "on_element_missing", ("skip", "abort"), default="skip"),
        save_debug_on_error=_as_bool(data.get("save_debug_on_error"), "save_debug_on_error", default=True),
        output_csv=_as_bool(data.get("output_csv"), "output_csv", default=False),
        body_as_markdown=_as_bool(data.get("body_as_markdown"), "body_as_markdown", default=False),
        lock_stale_minutes=_as_int(data.get("lock_stale_minutes"), "lock_stale_minutes", 1, 1440, default=60),
    )


def load_credentials(path: str = ".env.local") -> Credentials:
    """.env.local から認証情報を読み込む。

    SALON_EMAIL / SALON_PASSWORD が欠落・空の場合は ConfigError。
    値はログ出力しない。
    """
    p = Path(path)
    if not p.exists():
        raise ConfigError(
            f"認証情報ファイルがありません: {path}（.env.local.example をコピーして作成してください）"
        )
    values = dotenv_values(p)  # OS環境変数は混ぜず、ファイルの値のみ使用
    email = (values.get("SALON_EMAIL") or "").strip()
    password = values.get("SALON_PASSWORD") or ""
    if not email:
        raise ConfigError(f"{path}: SALON_EMAIL が未設定です")
    if not password:
        raise ConfigError(f"{path}: SALON_PASSWORD が未設定です")
    return Credentials(email=email, password=password)
