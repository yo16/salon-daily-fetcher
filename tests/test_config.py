"""config.py のテスト: 設定検証（型/範囲/プレースホルダ/欠落）と認証情報読込。"""

import pytest
import yaml

from src.config import load_config, load_credentials
from src.models import Config, ConfigError


def _valid_config_dict() -> dict:
    return {
        "login_url": "https://salon.jp/authentications/login",
        "list_url": "https://salon.jp/xxxx/articles",
        "selectors": {
            "login_email": "input[name='email']",
            "login_password": "input[name='password']",
            "login_submit": "button[type='submit']",
            "logged_in_mark": ".user-menu",
            "list_item": ".article-card",
            "item_author": ".user-name",
            "item_title": ".title",
            "item_date": ".date",
            "body": ".article-body",
            "item_image": ".thumb",
            "noise": [".ad", "nav"],
        },
        "author_filter": "西野亮廣エンタメ研究所",
        "headless": True,
        "timeout_ms": 15000,
        "throttle_seconds": 2,
        "max_items_per_run": 50,
        "order": "newest_first",
        "retry": {"max_attempts": 3, "backoff_seconds": 2},
        "on_login_failure": "abort",
        "on_element_missing": "skip",
        "save_debug_on_error": True,
        "output_csv": False,
        "body_as_markdown": False,
        "lock_stale_minutes": 60,
    }


def _write_config(tmp_path, data: dict) -> str:
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return str(p)


# --- 正常系 -------------------------------------------------------------------
def test_load_valid_config(tmp_path):
    cfg = load_config(_write_config(tmp_path, _valid_config_dict()))
    assert isinstance(cfg, Config)
    assert cfg.list_url.endswith("/articles")
    assert cfg.selectors.body == ".article-body"
    assert cfg.selectors.noise == [".ad", "nav"]
    assert cfg.selectors.item_author == ".user-name"
    assert cfg.selectors.item_image == ".thumb"
    assert cfg.author_filter == "西野亮廣エンタメ研究所"
    assert cfg.retry.max_attempts == 3
    assert cfg.throttle_seconds == 2.0


def test_defaults_when_optional_keys_absent(tmp_path):
    d = _valid_config_dict()
    for k in ["headless", "timeout_ms", "throttle_seconds", "max_items_per_run",
              "order", "retry", "on_login_failure", "on_element_missing",
              "save_debug_on_error", "output_csv", "body_as_markdown",
              "lock_stale_minutes"]:
        d.pop(k)
    cfg = load_config(_write_config(tmp_path, d))
    assert cfg.headless is True
    assert cfg.timeout_ms == 15000
    assert cfg.retry.max_attempts == 3
    assert cfg.on_login_failure == "abort"
    assert cfg.lock_stale_minutes == 60


# --- 異常系（検証） -----------------------------------------------------------
def test_placeholder_list_url_rejected(tmp_path):
    d = _valid_config_dict()
    d["list_url"] = "<対象サロンの記事一覧URL>"
    with pytest.raises(ConfigError):
        load_config(_write_config(tmp_path, d))


def test_placeholder_selector_rejected(tmp_path):
    d = _valid_config_dict()
    d["selectors"]["body"] = "<本文コンテナ>"
    with pytest.raises(ConfigError):
        load_config(_write_config(tmp_path, d))


def test_missing_required_selector_rejected(tmp_path):
    d = _valid_config_dict()
    del d["selectors"]["body"]
    with pytest.raises(ConfigError):
        load_config(_write_config(tmp_path, d))


def test_non_url_login_url_rejected(tmp_path):
    d = _valid_config_dict()
    d["login_url"] = "salon.jp/login"  # スキームなし
    with pytest.raises(ConfigError):
        load_config(_write_config(tmp_path, d))


def test_timeout_below_range_rejected(tmp_path):
    d = _valid_config_dict()
    d["timeout_ms"] = 999
    with pytest.raises(ConfigError):
        load_config(_write_config(tmp_path, d))


def test_max_items_above_range_rejected(tmp_path):
    d = _valid_config_dict()
    d["max_items_per_run"] = 1000
    with pytest.raises(ConfigError):
        load_config(_write_config(tmp_path, d))


def test_invalid_order_rejected(tmp_path):
    d = _valid_config_dict()
    d["order"] = "oldest_first"
    with pytest.raises(ConfigError):
        load_config(_write_config(tmp_path, d))


def test_invalid_on_login_failure_rejected(tmp_path):
    d = _valid_config_dict()
    d["on_login_failure"] = "retry"
    with pytest.raises(ConfigError):
        load_config(_write_config(tmp_path, d))


def test_non_bool_headless_rejected(tmp_path):
    d = _valid_config_dict()
    d["headless"] = "yes"
    with pytest.raises(ConfigError):
        load_config(_write_config(tmp_path, d))


def test_retry_out_of_range_rejected(tmp_path):
    d = _valid_config_dict()
    d["retry"]["max_attempts"] = 99
    with pytest.raises(ConfigError):
        load_config(_write_config(tmp_path, d))


def test_missing_config_file_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load_config(str(tmp_path / "nope.yaml"))


# --- 認証情報 -----------------------------------------------------------------
def test_load_valid_credentials(tmp_path):
    p = tmp_path / ".env.local"
    p.write_text("SALON_EMAIL=user@example.com\nSALON_PASSWORD=secret\n", encoding="utf-8")
    cred = load_credentials(str(p))
    assert cred.email == "user@example.com"
    assert cred.password == "secret"


def test_missing_email_rejected(tmp_path):
    p = tmp_path / ".env.local"
    p.write_text("SALON_EMAIL=\nSALON_PASSWORD=secret\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_credentials(str(p))


def test_missing_password_rejected(tmp_path):
    p = tmp_path / ".env.local"
    p.write_text("SALON_EMAIL=user@example.com\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_credentials(str(p))


def test_missing_credentials_file_rejected(tmp_path):
    with pytest.raises(ConfigError):
        load_credentials(str(tmp_path / ".env.local"))
