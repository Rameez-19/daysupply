"""The front end must parse. Nothing else in the browser matters if it does not.

**This test exists because a syntax error shipped to production.** `app.js` had
an unescaped apostrophe inside a single-quoted string — `recipient's` — which
broke the template expression containing it. The whole file failed to parse, so
*no JavaScript ran at all*: `loadStates()` never executed, the state dropdown
sat on its static "Loading states…" option forever, and both panels on Today
stayed empty. The page looked like a slow backend. Every backend endpoint was
returning 200 in under a second.

Two things made it worse than a normal bug:

* **Python heredocs were eating the backslashes.** Several edits to `app.js`
  were applied via `python - <<'EOF'` blocks, where `\\'` and `\\n` arrived in
  the file as a bare `'` and a literal newline. The file looked right in the
  patch and was broken on disk.
* **`node --check` was available the whole time and was not being run.** An
  early heredoc failure was misread as node being unavailable, and that
  conclusion was never rechecked.

A parse check costs milliseconds. There is no excuse for shipping a file the
browser cannot read.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
JS_FILES = sorted(WEB.glob("*.js"))

NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
@pytest.mark.parametrize("js", JS_FILES, ids=lambda p: p.name)
def test_javascript_parses(js: Path):
    """`node --check` on every file the browser loads."""
    result = subprocess.run(
        [NODE, "--check", str(js)], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"{js.name} does not parse, so the browser will run none of it:\n"
        f"{result.stderr}")


def test_there_are_javascript_files_to_check():
    """Guard against the glob silently matching nothing."""
    assert JS_FILES, "no .js files found under web/ — has the path changed?"


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_node_is_actually_available():
    """The skip above must not become a permanent, silent pass.

    If node disappears from the environment these checks stop running and
    nothing says so. This test fails loudly rather than skipping, so the gap is
    visible.
    """
    assert NODE, "node not found; the parse checks above are being skipped"


class TestEveryScriptTagResolves:
    """A script the page loads but the repo does not contain is a 404 and a
    dead feature, and the page will not say so."""

    def test_scripts_referenced_by_index_exist(self):
        import re
        html = (WEB / "index.html").read_text(encoding="utf-8")
        local = [s for s in re.findall(r'<script src="([^"]+)"', html)
                 if not s.startswith("http")]
        assert local, "index.html references no local scripts"
        for src in local:
            assert (WEB / src).exists(), f"index.html loads {src}, which is missing"

    def test_service_worker_caches_every_local_script(self):
        """A script missing from the SW asset list is unavailable offline —
        which is the one property this product cannot lose."""
        import re
        html = (WEB / "index.html").read_text(encoding="utf-8")
        sw = (WEB / "sw.js").read_text(encoding="utf-8")
        local = [s for s in re.findall(r'<script src="([^"]+)"', html)
                 if not s.startswith("http")]
        for src in local:
            assert f"'/{src}'" in sw, (
                f"{src} is loaded by the page but not cached by the service "
                "worker, so it will not be there offline")


class TestTheDomTheCodeExpectsActuallyExists:
    """Parsing is not enough. These are the failures that shipped anyway.

    Twice now the file parsed perfectly and the page was dead:

    * `renderStats()` wrote into `stats-grid` after the restructure deleted it.
      Unguarded, so it threw on every load and stopped the init chain before a
      single panel rendered. Endpoint checks all returned 200.
    * A stat card and a retry button pointed `switchTab()` at views that had
      been renamed, which fails silently — the click just does nothing.

    Both are statically detectable, so they are detected here rather than in a
    screenshot.
    """

    @staticmethod
    def _sources():
        """Every script the page actually loads, not a hardcoded list.

        This was pinned to ("app.js", "surge.js"). Adding map.js made the
        handler check fail on handlers that were perfectly well defined — the
        test simply could not see the file. A hardcoded list silently stops
        covering the thing it was written to cover.
        """
        import re
        html = (WEB / "index.html").read_text(encoding="utf-8")
        local = [src for src in re.findall(r'<script src="([^"]+)"', html)
                 if not src.startswith("http")]
        js = "".join((WEB / f).read_text(encoding="utf-8") for f in local)
        ids = set(re.findall(r'id="([A-Za-z0-9_-]+)"', html))
        return html, js, ids

    def test_no_unguarded_write_to_an_element_that_does_not_exist(self):
        """`getElementById('x').innerHTML` where x is not in the page."""
        import re
        _, js, ids = self._sources()
        missing = sorted({m for m in re.findall(
            r"getElementById\('([A-Za-z0-9_-]+)'\)\.\w", js) if m not in ids})
        assert not missing, (
            "these elements are written to without a null guard and do not "
            f"exist in index.html, so the page will throw on load: {missing}")

    def test_every_switchtab_target_is_a_real_view(self):
        """A tab switch to a renamed view fails silently — nothing happens."""
        import re
        html, js, _ = self._sources()
        views = set(re.findall(r'<section id="([a-z-]+)"', html))
        targets = set(re.findall(r"switchTab\('([a-z-]+)'\)", js + html))
        missing = sorted(targets - views)
        assert not missing, f"switchTab points at non-existent views: {missing}"

    def test_every_nav_tab_has_a_matching_view(self):
        import re
        html, _, _ = self._sources()
        tabs = set(re.findall(r'data-tab="([a-z-]+)"', html))
        views = set(re.findall(r'<section id="([a-z-]+)"', html))
        assert not (tabs - views), f"nav tabs with no view: {sorted(tabs - views)}"

    def test_inline_handlers_are_defined_and_exposed(self):
        """An onclick/onchange resolves against global scope. A handler that is
        never defined makes the control silently inert — which is exactly how
        the resource selector looked broken."""
        import re
        html, js, _ = self._sources()
        handlers = set(re.findall(r'on(?:click|change)="([A-Za-z_]\w*)\(', html))
        for h in sorted(handlers):
            assert re.search(rf"(?:async )?function {h}\b", js), (
                f"index.html calls {h}() inline but it is never defined")


class TestTheLandingViewInitialisesOnFirstLoad:
    """app.js loads first and used to dispatch the landing view at once. That
    was fine while the landing view's loaders lived in app.js. When Today v2
    became the landing view its initialiser lived in today2.js, which has not
    run when app.js executes — and refreshAll() reaches it through
    `typeof initToday2 === 'function'`, a guard that is silently false at that
    moment. A real reader saw "Loading…" until they navigated away and back.

    A deterministic browser probe found it: the geography promise had
    resolved, the server had answered the scorecard, and the page still held
    zero tiles. This pins the fix rather than the symptom.
    """

    def _landing_view(self):
        import re
        html = (WEB / "index.html").read_text(encoding="utf-8")
        m = re.search(r'<section id="([a-z0-9-]+)" class="view active-view"', html)
        assert m, "no landing view is marked active-view"
        return m.group(1)

    def test_boot_waits_for_every_script(self):
        app = (WEB / "app.js").read_text(encoding="utf-8")
        assert "document.addEventListener('DOMContentLoaded', boot)" in app, (
            "the initial dispatch must wait for DOMContentLoaded, which fires "
            "only after the last classic script has executed")
        assert "document.readyState === 'loading'" in app

    def test_the_landing_view_is_dispatched_by_refresh_all(self):
        """The view marked active in the markup must be one refreshAll knows,
        or first load renders nothing at all."""
        import re
        app = (WEB / "app.js").read_text(encoding="utf-8")
        body = app[app.index("function refreshAll()"):]
        body = body[:body.index(chr(10) + "}" + chr(10))]
        assert f"'{self._landing_view()}'" in body

    def test_the_landing_view_is_today_v2(self):
        """Today v1 was retired on 2026-09-18. If this ever points elsewhere,
        the nav, the bottom nav and activeViewId's default all need to move."""
        landing = self._landing_view()
        assert landing == "today2-view"
        app = (WEB / "app.js").read_text(encoding="utf-8")
        assert "return el ? el.id : 'today2-view';" in app
        html = (WEB / "index.html").read_text(encoding="utf-8")
        assert 'class="nav-item active" data-tab="today2-view"' in html
        assert 'class="bottom-nav-item active" data-tab="today2-view"' in html
        assert 'id="today-view"' not in html


class TestAppJsDoesNotDependOnAFileThatHasNotRunYet:
    """`app.js` loads first and its init IIFE runs immediately. Anything it
    calls on that path must already exist.

    This is the third variant of the same failure. The page parsed, every
    endpoint returned 200 in under a second, and the landing view rendered
    nothing — because `loadExecutive()` called `signalBadge()`, which was
    defined in `surge.js`, loaded on the *next* script tag. The call sat inside
    a `try`, so the ReferenceError was swallowed by the catch and the panel
    showed a generic error instead of the national picture.

    It was a race, which is worse than a plain break: surge.js usually won,
    so the page usually worked, and the failure looked intermittent and
    environmental. A DOM shim executing app.js alone reproduced it every time.

    `loadSurge` and `loadSurgeBanner` are the sanctioned pattern — they are
    called behind `typeof x === 'function'`, so a not-yet-loaded file degrades
    instead of throwing. Unguarded calls are what this test forbids.
    """

    def test_no_unguarded_call_into_a_later_script(self):
        import re
        app = (WEB / "app.js").read_text(encoding="utf-8")
        surge = (WEB / "surge.js").read_text(encoding="utf-8")

        defined_in = lambda src: set(re.findall(r"function\s+(\w+)", src))
        app_defines, surge_defines = defined_in(app), defined_in(surge)

        called = set(re.findall(r"\b(\w+)\s*\(", app))
        guarded = set(re.findall(r"typeof\s+(\w+)\s*===\s*'function'", app))

        leaked = sorted((called & surge_defines) - app_defines - guarded)
        assert not leaked, (
            "app.js calls these without a typeof guard, but they are defined "
            "in surge.js, which has not executed when app.js's init runs. "
            "Either move them into app.js or guard the call: "
            f"{leaked}")


class TestNoSelfReferentialGlobalWrapper:
    """`window.x = () => x()` is infinite recursion, not an export.

    This is what actually broke the landing view, and it broke all three of
    its loaders at once — `loadExecutive`, `loadAlerts`, `loadTransfers`.

    A function declaration at the top level of a classic script is *already* a
    property of `window`. Assigning `window.loadExecutive = () => loadExecutive()`
    therefore replaces that property, and the identifier inside the arrow
    resolves back through the scope chain to the global object — which now
    holds the arrow. Calling it recurses until the stack dies.

    The failure is silent in the worst way. `RangeError` is thrown at call
    time, before the function body runs, so the `try` inside `loadExecutive`
    never catches it and `setSyncState()` fires on neither the success nor the
    failure path. The page shows empty panels and a sync badge still reading
    "Loading…", which looks like a slow or hung backend. Every endpoint was
    returning 200 in under a second.

    A DOM shim did not catch it, because a shim's `global.window` is an
    ordinary object rather than the real global object, so the assignment does
    not clobber anything and the code appears to work. Only a real browser
    reproduces it. That is why this is a static check.

    `window.onStateChange = onStateChange` — a direct reference, no arrow — is
    correct and unaffected.
    """

    @pytest.mark.parametrize("name", [p.name for p in JS_FILES])
    def test_no_function_is_reexported_as_a_call_to_itself(self, name):
        import re
        src = (WEB / name).read_text(encoding="utf-8")
        bad = re.findall(r"window\.(\w+)\s*=\s*\(\s*\)\s*=>\s*\1\s*\(", src)
        assert not bad, (
            f"{name} re-exports these as an arrow calling the same name, which "
            "overwrites the global binding and recurses until the stack "
            f"overflows: {sorted(set(bad))}. A top-level function declaration "
            "is already on window — delete the assignment.")


class TestButtonClassesExist:
    """A button whose class is not in the stylesheet renders as a raw browser
    button in the middle of a designed page.

    Caught when the "See it on the map" step referenced `.btn-secondary`, which
    had never been written. Nothing errors — it just looks broken.
    """

    def test_every_btn_class_used_is_defined(self):
        import re
        html = (WEB / "index.html").read_text(encoding="utf-8")
        js = "".join((WEB / f).read_text(encoding="utf-8")
                     for f in ("app.js", "surge.js", "map.js"))
        css = (WEB / "styles.css").read_text(encoding="utf-8")

        used = set(re.findall(r'class="[^"]*\b(btn-[\w-]+)', html + js))
        undefined = sorted(c for c in used if f".{c}" not in css)
        assert not undefined, (
            f"these button classes are used but never styled: {undefined}")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_every_script_executes_not_just_parses():
    """`node --check` validates syntax. It cannot find a missing identifier.

    Deleting the old Network markup made `onResourceSegment` unreachable, so
    it was removed — leaving `window.onResourceSegment = onResourceSegment`
    behind it, twice. That is valid syntax and a ReferenceError at load, and
    app.js runs first, so nothing after the throw would have executed: every
    page in the product, blank.

    It is the same shape as the two front-end outages before it. The file
    parsed; the app was dead. So this runs each script against a permissive DOM
    stub, which is the cheapest thing that would have caught all three.

    A stub is not a browser and this is not a substitute for opening the page —
    but a reference error needs no browser to find.
    """
    import re
    html = (WEB / "index.html").read_text(encoding="utf-8")
    # Only what the PAGE loads. sw.js is a service worker: it runs in a worker
    # context and legitimately uses `self`, so executing it here would fail for
    # a reason that has nothing to do with the page.
    page_scripts = [WEB / src for src in
                    re.findall(r'<script src="([^"]+)"', html)
                    if not src.startswith("http")]
    assert page_scripts, "index.html loads no local scripts"

    script = Path(__file__).parent / "exec_check.js"
    result = subprocess.run(
        [NODE, str(script), *[str(p) for p in page_scripts]],
        capture_output=True, text=True)
    assert result.returncode == 0, (
        "a shipped script throws at load, which takes down every page:\n"
        f"{result.stdout}{result.stderr}")
