"""scaffold スモークテスト: 設定ファイル雛形とパッケージ構成の健全性を確認する。"""

import importlib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _load_config() -> dict:
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def test_config_yaml_is_valid_mapping():
    data = _load_config()
    assert isinstance(data, dict)


def test_config_yaml_has_required_top_level_keys():
    data = _load_config()
    required = [
        "login_url", "list_url", "selectors", "headless", "timeout_ms",
        "throttle_seconds", "max_items_per_run", "order", "retry",
        "on_login_failure", "on_element_missing",
    ]
    for key in required:
        assert key in data, f"missing top-level key: {key}"


def test_config_yaml_has_required_selectors():
    selectors = _load_config()["selectors"]
    required = [
        "login_email", "login_password", "login_submit", "logged_in_mark",
        "list_item", "item_link", "item_title", "item_date", "body",
    ]
    for sel in required:
        assert sel in selectors, f"missing selector: {sel}"


def test_env_example_declares_credentials():
    text = (ROOT / ".env.local.example").read_text(encoding="utf-8")
    assert "SALON_EMAIL" in text
    assert "SALON_PASSWORD" in text


def test_src_package_is_importable():
    assert importlib.import_module("src") is not None
