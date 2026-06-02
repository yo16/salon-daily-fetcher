"""対象サロン専用のブラウザ操作（Playwright）: login / extract_list / fetch_body。

設計: docs/design.md §5.3, §6
- URL/セレクタは config 参照（コードに直書きしない）。
- 純粋ロジック（ID採番・日付正規化・本文整形・リトライ）は textutil に分離。
- 一過性の失敗はリトライ、最終失敗は on_element_missing / 例外で扱う。
"""

from datetime import date
from urllib.parse import urljoin

from playwright.sync_api import Error as PWError

from .models import ArticleMeta, Config, Credentials, ExtractionError, LoginError
from .textutil import clean_text, derive_id, normalize_date, with_retry


def login(page, config: Config, creds: Credentials, logger=None) -> None:
    """ログインフローを実行する。ログイン後要素が出なければ LoginError。"""
    sel = config.selectors
    try:
        page.goto(config.login_url, timeout=config.timeout_ms)
        page.fill(sel.login_email, creds.email, timeout=config.timeout_ms)
        page.fill(sel.login_password, creds.password, timeout=config.timeout_ms)
        page.click(sel.login_submit, timeout=config.timeout_ms)
        page.wait_for_selector(sel.logged_in_mark, timeout=config.timeout_ms)
    except PWError as e:
        raise LoginError("ログインに失敗しました（ログイン後要素が表示されません）") from e


def extract_list(page, config: Config, today: date | None = None, logger=None) -> list[ArticleMeta]:
    """記事一覧ページから各記事の id/title/date/url を抽出する（newest_first 前提）。"""
    sel = config.selectors

    def _open_and_collect():
        page.goto(config.list_url, timeout=config.timeout_ms)
        page.wait_for_selector(sel.list_item, timeout=config.timeout_ms)
        return page.query_selector_all(sel.list_item)

    items = with_retry(
        _open_and_collect,
        attempts=config.retry.max_attempts,
        backoff=config.retry.backoff_seconds,
        logger=logger, label="extract_list", exc=(PWError,),
    )

    metas: list[ArticleMeta] = []
    for el in items:
        link_el = el.query_selector(sel.item_link)
        if link_el is None:
            continue
        href = link_el.get_attribute("href") or ""
        url = urljoin(config.list_url, href)
        title_el = el.query_selector(sel.item_title)
        date_el = el.query_selector(sel.item_date)
        title = title_el.inner_text().strip() if title_el else ""
        raw_date = date_el.inner_text().strip() if date_el else ""
        try:
            d = normalize_date(raw_date, today)
        except ValueError:
            d = (today or date.today()).isoformat()
            if logger is not None:
                logger.warning(f"extract_list: 日付解析不可 raw={raw_date!r} → {d} を使用")
        metas.append(ArticleMeta(id=derive_id(url), title=title, date=d, url=url))

    if not metas and config.on_element_missing == "abort":
        raise ExtractionError("一覧から記事を抽出できませんでした")
    return metas


def fetch_body(page, config: Config, url: str, logger=None) -> str:
    """記事ページの本文をクリーンテキストで取得する。"""
    sel = config.selectors

    def _open():
        page.goto(url, timeout=config.timeout_ms)
        page.wait_for_selector(sel.body, timeout=config.timeout_ms)

    with_retry(
        _open,
        attempts=config.retry.max_attempts,
        backoff=config.retry.backoff_seconds,
        logger=logger, label="fetch_body", exc=(PWError,),
    )

    # ノイズ要素（広告・ナビ等）を除去してから本文を取得
    for noise in sel.noise:
        try:
            page.eval_on_selector_all(noise, "els => els.forEach(e => e.remove())")
        except PWError:
            pass

    body_el = page.query_selector(sel.body)
    if body_el is None:
        if config.on_element_missing == "abort":
            raise ExtractionError(f"本文要素が見つかりません: {url}")
        return ""

    if config.body_as_markdown:
        text = _html_to_markdown(body_el.inner_html())
    else:
        text = body_el.inner_text()
    return clean_text(text)


def _html_to_markdown(html: str) -> str:
    """HTML を Markdown に変換（markdownify があれば使用、無ければ素の文字列）。"""
    try:
        from markdownify import markdownify as md
        return md(html)
    except Exception:
        return html
