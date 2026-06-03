"""ログイン後の記事一覧/記事ページの構造ダンプ（セレクタ確定用・一時的な調査スクリプト）。

- ログイン → /nishino タイムラインを取得。
- 各投稿の .user-name を見て、対象投稿者の投稿だけを抽出。
- 対象投稿のリンク/タイトル/日時候補をダンプ、最初の記事ページの本文候補もダンプ。
- パスワードは出力しない。出力は logs/debug/inspect/ にも保存。

実行: python scripts/inspect_list.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import json  # noqa: E402

import yaml  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from src.config import load_credentials  # noqa: E402

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")

LIST_URL = "https://salon.jp/nishino"
TARGET_AUTHOR = "西野亮廣エンタメ研究所"
ITEM_SEL = "#js-timeline-container > div > div.timeline-view-all > div"

_LEAF_JS = """e => Array.from(e.querySelectorAll('*'))
  .filter(n => n.children.length === 0 && n.textContent.trim())
  .slice(0, 40)
  .map(n => ({cls: (typeof n.className==='string'? n.className:''), tag: n.tagName, text: n.textContent.trim().slice(0,50)}))"""

_ANCHORS_JS = """e => Array.from(e.querySelectorAll('a'))
  .map(a => ({href: a.getAttribute('href'), cls: (typeof a.className==='string'? a.className:''), text: a.textContent.trim().slice(0,40)}))"""

_BODY_CANDIDATES_JS = """() => Array.from(document.querySelectorAll('*'))
  .map(n => ({cls: (typeof n.className==='string'? n.className:''), tag: n.tagName, len: n.textContent.trim().length}))
  .filter(x => x.len > 200)
  .sort((a,b) => b.len - a.len)
  .slice(0, 15)"""


def main() -> int:
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    sel = cfg["selectors"]
    timeout = int(cfg.get("timeout_ms", 15000))
    headless = bool(cfg.get("headless", True))
    creds = load_credentials(str(ROOT / ".env.local"))

    out = ROOT / "logs" / "debug" / "inspect"
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=_UA, locale="ja-JP")
        page = context.new_page()
        page.set_default_timeout(timeout)

        # --- login ---
        page.goto(cfg["login_url"], wait_until="domcontentloaded")
        page.fill(sel["login_email"], creds.email)
        page.fill(sel["login_password"], creds.password)
        page.click(sel["login_submit"])
        try:
            page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            pass
        print(f"[login] -> {page.url}")

        # --- timeline ---
        page.goto(LIST_URL, wait_until="domcontentloaded")
        try:
            page.wait_for_selector("#js-timeline-container", timeout=timeout)
            page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            pass
        items = page.query_selector_all(ITEM_SEL)
        print(f"[timeline] items matched by ITEM_SEL = {len(items)}")

        target_indices = []
        for idx, el in enumerate(items, 1):
            un = el.query_selector(".user-name")
            author = un.inner_text().strip() if un else ""
            is_target = author == TARGET_AUTHOR
            if is_target:
                target_indices.append(idx)
            if idx <= 8:
                anchors = el.evaluate(_ANCHORS_JS)
                print(f"  [{idx}] author={author!r} target={is_target}")
                for a in anchors:
                    print(f"       a: href={a['href']!r} cls={a['cls']!r} text={a['text']!r}")
        print(f"[timeline] target posts (author=={TARGET_AUTHOR!r}) at indices: {target_indices}")

        if not target_indices:
            print("[WARN] 対象投稿者の投稿が見つかりませんでした。ITEM_SEL/TARGET_AUTHOR を確認してください。")
            (out / "timeline.html").write_text(page.content(), encoding="utf-8")
            browser.close()
            return 1

        # --- first target post detail ---
        first = items[target_indices[0] - 1]
        (out / "first_post.html").write_text(first.evaluate("e => e.outerHTML"), encoding="utf-8")
        leaves = first.evaluate(_LEAF_JS)
        anchors = first.evaluate(_ANCHORS_JS)
        print("\n[first target post] leaf texts (cls : text):")
        for lf in leaves:
            print(f"    {lf['tag']}.{lf['cls']} : {lf['text']!r}")
        print("[first target post] anchors:")
        for a in anchors:
            print(f"    href={a['href']!r} cls={a['cls']!r} text={a['text']!r}")

        # 記事リンクの推定: 最初の非空 href（要レビュー）
        article_href = next((a["href"] for a in anchors if a["href"]), None)
        print(f"\n[guess] article_href = {article_href!r}")

        if article_href:
            url = article_href if article_href.startswith("http") else ("https://salon.jp" + article_href if article_href.startswith("/") else None)
            if url:
                page.goto(url, wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state("networkidle", timeout=timeout)
                except Exception:
                    pass
                print(f"\n[article] opened {page.url} | title={page.title()!r}")
                (out / "article.html").write_text(page.content(), encoding="utf-8")
                cands = page.evaluate(_BODY_CANDIDATES_JS)
                print("[article] body container candidates (len desc):")
                for c in cands:
                    print(f"    {c['tag']}.{c['cls']} : len={c['len']}")

        browser.close()
    print(f"\n[saved] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
