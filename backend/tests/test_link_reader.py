import pytest

from stockllm.link_reader import LinkReadUnavailable, _extract_html, extract_allowed_urls


def test_extract_allowed_urls_rejects_unregistered_domains() -> None:
    urls = extract_allowed_urls(
        "查看 https://finance.eastmoney.com/a/example.html 和 http://127.0.0.1/private "
        "以及 https://example.com/news"
    )
    assert urls == ["https://finance.eastmoney.com/a/example.html"]


def test_extract_html_uses_article_body_instead_of_page_navigation() -> None:
    title, text, truncated = _extract_html(
        b"<html><head><title>Test title</title></head><body><nav>navigation</nav>"
        b"<div id='ContentBody'><p>This is the first paragraph with enough detail for research.</p>"
        b"<p>This is the second paragraph with additional verifiable context.</p></div></body></html>",
        "https://finance.eastmoney.com/a/example.html",
    )
    assert title == "Test title"
    assert "first paragraph" in text
    assert "navigation" not in text
    assert not truncated


def test_extract_html_rejects_pages_without_a_reliable_body() -> None:
    with pytest.raises(LinkReadUnavailable):
        _extract_html(
            b"<html><body><nav>Only navigation</nav></body></html>",
            "https://finance.eastmoney.com/a/example.html",
        )
