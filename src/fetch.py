"""対象サロン専用のブラウザ操作（Playwright）: login / extract_articles。

設計: docs/design.md §5.3, §6（実サイト構造に合わせて調整）
- タイムラインは複数投稿者が混在 → author_filter で対象投稿者の投稿のみ抽出。
- 本文は個別ページへ遷移せず、タイムライン内(list_item)からインライン取得。
- 記事IDは画像 src の /articles/<id>/ から、無ければ本文ハッシュ。
- URL/セレクタは config 参照（コードに直書きしない）。
"""

from datetime import date, datetime

from playwright.sync_api import Error as PWError

from .models import Article, ArticleMeta, Config, Credentials, ExtractionError, LoginError
from .textutil import article_id_from_src, clean_text, hash_id, normalize_date, with_retry


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _text(el) -> str:
    return el.inner_text().strip() if el else ""


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


def _article_id(el, sel, body: str) -> str:
    """記事IDを決定する。画像 src の /articles/<id>/ を優先、無ければ本文ハッシュ。"""
    if sel.item_image:
        img = el.query_selector(sel.item_image)
        if img is not None:
            aid = article_id_from_src(img.get_attribute("src"))
            if aid:
                return aid
    return hash_id(body)


def _body_text(el, sel, body_as_markdown: bool) -> str:
    body_el = el.query_selector(sel.body)
    if body_el is None:
        return ""
    if body_as_markdown:
        return clean_text(_html_to_markdown(body_el.inner_html()))
    # text_content() は CSS のホワイトスペース折りたたみを行わず、原文の改行を保持する
    # （inner_text() だと段落改行がスペースに潰れてしまう）
    return clean_text(body_el.text_content() or "")


def extract_articles(page, config: Config, today: date | None = None, logger=None) -> list[Article]:
    """タイムラインから対象投稿者の投稿を抽出し、本文込みの Article を返す（newest_first）。"""
    sel = config.selectors

    def _open():
        page.goto(config.list_url, timeout=config.timeout_ms)
        page.wait_for_selector(sel.list_item, timeout=config.timeout_ms)
        return page.query_selector_all(sel.list_item)

    items = with_retry(
        _open,
        attempts=config.retry.max_attempts,
        backoff=config.retry.backoff_seconds,
        logger=logger, label="extract", exc=(PWError,),
    )

    articles: list[Article] = []
    for el in items:
        author = _text(el.query_selector(sel.item_author))
        if config.author_filter and author != config.author_filter:
            continue
        title = _text(el.query_selector(sel.item_title))
        body = _body_text(el, sel, config.body_as_markdown)
        if not body and not title:
            continue
        raw_date = _text(el.query_selector(sel.item_date))
        try:
            d = normalize_date(raw_date, today)
        except ValueError:
            d = (today or date.today()).isoformat()
            if logger is not None:
                logger.warning(f"extract: 日付解析不可 raw={raw_date!r} → {d} を使用")
        aid = _article_id(el, sel, body)
        meta = ArticleMeta(id=aid, title=title, date=d, url=f"{config.list_url}#{aid}")
        articles.append(Article(meta=meta, body=body, fetched_at=_now()))

    if not articles and config.on_element_missing == "abort":
        raise ExtractionError("一覧から対象投稿を抽出できませんでした")
    return articles


def _html_to_markdown(html: str) -> str:
    """HTML を Markdown に変換（markdownify があれば使用、無ければ素の文字列）。"""
    try:
        from markdownify import markdownify as md
        return md(html)
    except Exception:
        return html
