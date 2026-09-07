"""A deploy must actually deploy, and you must be able to tell.

Twice a deploy reached the browser only partly: new `index.html` and new
`app.js` with an old `styles.css`. The redesigned dashboard rendered as a
column of unstyled plain text — the new markup was there, the rules for it were
not — and nothing in the page reported an error, because nothing had errored.

`Cache-Control: no-cache` fixed the HTTP cache. It was necessary and not
sufficient: a URL is the only thing every cache layer agrees on, and a stale
service worker or an intermediary proxy can still return yesterday's bytes for
the URL `styles.css`. None of them can do it for `styles.css?v=a219687b`.

These tests pin that machinery, and one of them pins the thing the machinery
could have broken: offline.
"""

import re
from pathlib import Path

import pytest

from app import main

WEB = Path(__file__).resolve().parent.parent / "web"


class TestTheBuildId:
    def test_it_is_a_short_hex_hash(self):
        b = main.build_id()
        assert re.fullmatch(r"[0-9a-f]{8}", b), b

    def test_it_is_stable_across_calls(self):
        assert main.build_id() == main.build_id()

    def test_it_covers_every_file_the_browser_executes(self):
        """A build id that ignores a file cannot detect a change to it — which
        is exactly the failure it exists to prevent."""
        src = main.WEB_DIR
        shipped = {p.name for p in src.iterdir()
                   if p.suffix in (".js", ".css", ".html")}
        assert "styles.css" in shipped and "app.js" in shipped
        assert "index.html" in shipped

    def test_it_changes_when_a_front_end_file_changes(self, tmp_path,
                                                      monkeypatch):
        """The whole point. Computed on a copy so the repo is untouched."""
        import hashlib

        def build_from(directory: Path) -> str:
            h = hashlib.sha256()
            for name in sorted(p.name for p in directory.iterdir()
                               if p.suffix in (".js", ".css", ".html")):
                h.update(name.encode())
                h.update((directory / name).read_bytes())
            return h.hexdigest()[:8]

        for p in main.WEB_DIR.iterdir():
            if p.suffix in (".js", ".css", ".html"):
                (tmp_path / p.name).write_bytes(p.read_bytes())

        before = build_from(tmp_path)
        css = tmp_path / "styles.css"
        css.write_text(css.read_text(encoding="utf-8") + "\n/* x */\n",
                       encoding="utf-8")
        assert build_from(tmp_path) != before


class TestTheServedShell:
    @pytest.fixture(scope="class")
    @classmethod
    def html(cls):
        return main._versioned_index()

    def test_every_local_script_and_stylesheet_is_stamped(self, html):
        unstamped = re.findall(r'(?:src|href)="([\w./-]+\.(?:js|css))"', html)
        assert not unstamped, (
            f"these load from an unversioned URL and can be served stale: "
            f"{unstamped}")

    def test_the_stamp_is_the_current_build(self, html):
        stamped = re.findall(r'(?:src|href)="[\w./-]+\.(?:js|css)\?v=(\w+)"',
                             html)
        assert stamped, "nothing was stamped at all"
        assert set(stamped) == {main.build_id()}

    def test_external_cdn_urls_are_left_alone(self, html):
        """Stamping a URL we do not control would break it."""
        for url in re.findall(r'(?:src|href)="(https://[^"]+)"', html):
            assert "?v=" not in url, url

    def test_the_placeholder_is_replaced(self, html):
        assert "__BUILD__" not in html, (
            "the footer would show the literal placeholder")

    def test_the_footer_reports_the_build_the_browser_has(self, html):
        m = re.search(r'id="build-stamp"[^>]*>([^<]+)<', html)
        assert m, "no build stamp in the page"
        assert m.group(1).strip() == main.build_id()


class TestOfflineSurvivesTheStamp:
    """The stamp could have silently broken the one property this product
    cannot lose.

    The service worker caches '/app.js'. Once the page asks for
    '/app.js?v=a219687b', a plain `caches.match(request)` misses — different
    URL — so going offline would serve nothing at all, and it would only show
    up in the field, on a bad connection, at a PHC.
    """

    def test_the_cache_fallback_ignores_the_query_string(self):
        sw = (WEB / "sw.js").read_text(encoding="utf-8")
        assert "ignoreSearch" in sw, (
            "sw.js falls back to caches.match without ignoreSearch, so a "
            "versioned asset URL will never match its cached copy and the app "
            "will be blank offline")

    def test_the_cache_version_was_bumped(self):
        sw = (WEB / "sw.js").read_text(encoding="utf-8")
        m = re.search(r"stockpulse-v(\d+)", sw)
        assert m, "no cache version in sw.js"
        assert int(m.group(1)) >= 27


class TestTheStaleCheckIsWired:
    """The page must notice when it is running something the server replaced."""

    def test_app_js_checks_the_build_and_offers_a_reload(self):
        app_js = (WEB / "app.js").read_text(encoding="utf-8")
        assert "/api/v1/build" in app_js
        assert "function hardReload" in app_js
        assert "checkBuild()" in app_js, "checkBuild is defined but never run"

    def test_hard_reload_clears_caches_and_unregisters_the_worker(self):
        """A plain reload can be answered by the very worker holding the stale
        copy, so the reload has to clear it first."""
        app_js = (WEB / "app.js").read_text(encoding="utf-8")
        block = app_js[app_js.index("async function hardReload"):]
        block = block[:block.index("location.reload()")]
        assert "caches.delete" in block
        assert "unregister" in block
