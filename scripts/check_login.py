"""ログイン疎通の診断スクリプト（一時的な確認用・本体フローとは独立）。

- config.yaml の login_url とログインセレクタ、.env.local の認証情報を使う。
- ログインフォームの実構造をダンプし、セレクタが合わなければ自動検出にフォールバック。
- ログイン後のURL/フォーム有無で成否を推定し、スクショ/HTMLを logs/debug/login-check/ に保存。
- パスワードは一切出力しない。

実行: python scripts/check_login.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from src.config import load_credentials  # noqa: E402

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")


def _first_match(page, candidates):
    for c in candidates:
        if c and page.query_selector(c):
            return c
    return None


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    login_url = cfg["login_url"]
    sel = cfg.get("selectors", {})
    timeout = int(cfg.get("timeout_ms", 15000))
    headless = bool(cfg.get("headless", True))

    creds = load_credentials(str(ROOT / ".env.local"))
    masked = creds.email[:2] + "***"
    if "@" in creds.email:
        masked += "@" + creds.email.split("@", 1)[1]
    print(f"[info] login_url = {login_url}")
    print(f"[info] email     = {masked}")
    print(f"[info] headless  = {headless}")

    debug_dir = ROOT / "logs" / "debug" / "login-check"
    debug_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=_UA, locale="ja-JP")
        page = context.new_page()
        page.set_default_timeout(timeout)

        page.goto(login_url, wait_until="domcontentloaded")
        print(f"[step] opened: {page.url}")
        print(f"[step] title : {page.title()}")

        # --- ログインフォームの実構造をダンプ ---
        inputs = page.eval_on_selector_all(
            "input",
            "els => els.map(e => ({name:e.name, id:e.id, type:e.type, ph:e.placeholder}))",
        )
        buttons = page.eval_on_selector_all(
            "button, input[type=submit]",
            "els => els.map(e => ({tag:e.tagName, type:e.type, text:(e.innerText||e.value||'').trim().slice(0,30)}))",
        )
        print(f"[form] inputs  = {inputs}")
        print(f"[form] buttons = {buttons}")

        # --- セレクタ決定（config優先→自動検出フォールバック）---
        email_sel = _first_match(page, [
            sel.get("login_email"), "input[type='email']",
            "input[name*='mail' i]", "input[name='login']", "input[name='username']",
        ])
        pw_sel = _first_match(page, [sel.get("login_password"), "input[type='password']"])
        submit_sel = _first_match(page, [
            sel.get("login_submit"), "button[type='submit']",
            "input[type='submit']", "button",
        ])
        print(f"[sel ] email={email_sel!r} password={pw_sel!r} submit={submit_sel!r}")

        if not (email_sel and pw_sel and submit_sel):
            print("[FAIL] ログインフォームの項目を特定できませんでした。上の inputs/buttons を確認してください。")
            page.screenshot(path=str(debug_dir / "login_page.png"), full_page=True)
            (debug_dir / "login_page.html").write_text(page.content(), encoding="utf-8")
            browser.close()
            return 2

        # --- ログイン試行 ---
        page.fill(email_sel, creds.email)
        page.fill(pw_sel, creds.password)
        page.screenshot(path=str(debug_dir / "before_submit.png"))
        page.click(submit_sel)
        try:
            page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            pass

        print(f"[step] after submit url  : {page.url}")
        print(f"[step] after submit title: {page.title()}")
        page.screenshot(path=str(debug_dir / "after_submit.png"), full_page=True)
        (debug_dir / "after_submit.html").write_text(page.content(), encoding="utf-8")

        # --- 成否の推定 ---
        still_login = "login" in page.url.lower()
        has_password = page.query_selector("input[type='password']") is not None
        if still_login or has_password:
            print("[VERDICT] ログイン失敗の可能性が高い "
                  f"(login画面のまま={still_login}, パスワード欄が残存={has_password})")
            print(f"[hint] スクショ/HTML: {debug_dir}")
            browser.close()
            return 1

        print("[VERDICT] ログイン成功の可能性が高い（login画面から遷移し、パスワード欄が消失）")
        print(f"[hint] 遷移先 {page.url} を logged_in_mark の手掛かりに使えます。スクショ: {debug_dir}")
        browser.close()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
