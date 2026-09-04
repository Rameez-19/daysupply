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
        import re
        html = (WEB / "index.html").read_text(encoding="utf-8")
        js = "".join((WEB / f).read_text(encoding="utf-8")
                     for f in ("app.js", "surge.js"))
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
