from datetime import UTC, datetime

from jobseeker_assistant import ingest, snapshots

FIXED_NOW = lambda: datetime(2026, 11, 3, 12, 0, tzinfo=UTC)  # noqa: E731


def test_read_url_list_skips_comments_and_notes(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("# header\n\nhttps://a.test/x   # note\nhttps://b.test/y\n")
    assert ingest.read_url_list(f) == ["https://a.test/x", "https://b.test/y"]


def test_html_to_text_keeps_content_and_headings(sample_html):
    title, body = ingest.html_to_text(sample_html)
    assert title == "Pay subsidy"
    assert "## Amount" in body and "### When to apply" in body
    assert "- First list item" in body
    assert body.count("Nested paragraph item.") == 1


def test_html_to_text_drops_page_furniture(sample_html):
    _, body = ingest.html_to_text(sample_html)
    for junk in ("Menu item", "Cookie settings", "var x"):
        assert junk not in body


def test_ingest_saves_snapshot_with_url_and_date(tmp_path, sample_html):
    report = ingest.ingest(
        ["https://a.test/pay"], tmp_path, fetch=lambda u: sample_html, now=FIXED_NOW
    )
    assert report.saved == ["https://a.test/pay"]
    [snap] = snapshots.load_all(tmp_path)
    assert snap.url == "https://a.test/pay"
    assert snap.fetched_at == "2026-11-03T12:00:00+00:00"


def test_ingest_never_overwrites_without_refresh(tmp_path, sample_html):
    calls = []

    def fetch(url):
        calls.append(url)
        return sample_html

    ingest.ingest(["https://a.test/pay"], tmp_path, fetch=fetch, now=FIXED_NOW)
    report = ingest.ingest(["https://a.test/pay"], tmp_path, fetch=fetch, now=FIXED_NOW)
    assert report.skipped == ["https://a.test/pay"] and len(calls) == 1
    ingest.ingest(["https://a.test/pay"], tmp_path, refresh=True, fetch=fetch, now=FIXED_NOW)
    assert len(calls) == 2


def test_ingest_reports_failures_and_blocked_hosts(tmp_path):
    def fetch(url):
        raise ConnectionError("403 from proxy")

    report = ingest.ingest(
        ["https://blocked.test/a", "https://blocked.test/b"], tmp_path, fetch=fetch
    )
    assert len(report.failed) == 2
    assert report.blocked_hosts() == ["blocked.test"]
    assert list(tmp_path.glob("*.md")) == []


def test_ingest_rejects_nearly_empty_pages(tmp_path):
    report = ingest.ingest(
        ["https://a.test/js"],
        tmp_path,
        fetch=lambda u: "<html><body><main>Loading…</main></body></html>",
    )
    assert "almost no text" in report.failed["https://a.test/js"]


def test_main_returns_error_code_when_fetch_fails(tmp_path, monkeypatch, capsys):
    urls = tmp_path / "urls.txt"
    urls.write_text("https://blocked.test/a\n")
    monkeypatch.setattr(snapshots, "DEFAULT_SOURCES_DIR", tmp_path)
    monkeypatch.setattr(ingest, "http_get", lambda u: (_ for _ in ()).throw(OSError("denied")))
    assert ingest.main(["--urls", str(urls)]) == 1
    assert "blocked.test" in capsys.readouterr().out


def test_html_to_text_ignores_small_promo_article_when_no_main():
    html = (
        "<html><head><title>Long unemployment - Situations - Job Market Finland</title></head>"
        "<body><div><h2>Services</h2><p>"
        + "Real rules text about work try-out. "
        * 20
        + "</p></div>"
        "<article><h3>Promo</h3><p>Create a job applicant profile.</p></article></body></html>"
    )
    title, body = ingest.html_to_text(html)
    assert "Real rules text" in body and "## Services" in body
    assert title == "Long unemployment"


def test_html_to_text_uses_article_when_it_is_the_content():
    html = (
        "<html><body><div>Small sidebar</div><article><h1>News</h1><p>"
        + "Article text. " * 30
        + "</p></article></body></html>"
    )
    title, body = ingest.html_to_text(html)
    assert title == "News" and "Small sidebar" not in body


def test_clean_title_strips_site_suffix():
    assert ingest._clean_title("Pay subsidy - Services - Job Market Finland") == "Pay subsidy"
    assert ingest._clean_title("Kela | Home") == "Kela"
    assert ingest._clean_title("TE24 – reforms") == "TE24 – reforms"
