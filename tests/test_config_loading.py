"""Configuration loading — specifically, that `.env` is read at all.

`python-dotenv` sat in requirements.txt and `.env.example` sat in the repo root
for weeks while **nothing ever called `load_dotenv()`**. A `.env` file would
have been read by nobody, and the template implied a mechanism that did not
exist. That is a quiet kind of wrong: it fails by doing nothing.

These tests pin the fix, and in particular pin the one property that makes it
work — the *position* of the call.
"""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

MAIN = ROOT / "app" / "main.py"


def _module_ast() -> ast.Module:
    return ast.parse(MAIN.read_text(encoding="utf-8"))


def _line_of_load_dotenv_call(tree: ast.Module) -> int:
    for node in tree.body:
        if (isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Name)
                and node.value.func.id == "load_dotenv"):
            return node.lineno
    raise AssertionError(
        "app/main.py never calls load_dotenv(). python-dotenv is a dependency "
        "and .env.example exists, so a .env file must actually be read.")


def _first_app_import_line(tree: ast.Module) -> int:
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "app"):
            return node.lineno
    raise AssertionError("app/main.py imports nothing from app.*")


class TestDotenvIsLoaded:
    def test_load_dotenv_is_called(self):
        _line_of_load_dotenv_call(_module_ast())

    def test_it_runs_before_any_app_import(self):
        """The position is load-bearing, not stylistic.

        Modules under app/ read configuration at *import* time —
        `PROJECT = os.getenv("GCP_PROJECT", "daysupply")` executes when the
        module is first imported, not when a function is called. If
        load_dotenv() ran after those imports, every such constant would
        already be bound to its default and the .env file would silently do
        nothing. A linter or a tidy-up that moves the call down into the import
        block would reintroduce exactly the bug this replaced, without failing
        anything else.
        """
        tree = _module_ast()
        assert _line_of_load_dotenv_call(tree) < _first_app_import_line(tree), (
            "load_dotenv() must run before the first `from app import ...`; "
            "app modules read os.getenv at import time, so a later call is "
            "too late to have any effect")

    def test_dotenv_is_a_declared_dependency(self):
        requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
        assert re.search(r"^python-dotenv", requirements, re.M), (
            "app/main.py imports dotenv, so it must be pinned in "
            "requirements.txt or the container will fail to start")


class TestEnvExampleMatchesReality:
    """The template must not describe variables the code never reads."""

    def test_every_documented_variable_is_actually_read(self):
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        documented = {
            line.split("=", 1)[0].strip()
            for line in example.splitlines()
            if "=" in line and not line.strip().startswith("#")
        }
        assert documented, ".env.example documents no variables"

        sources = "\n".join(
            p.read_text(encoding="utf-8")
            for p in (ROOT / "app").glob("*.py")
        )
        for name in documented:
            assert f'"{name}"' in sources or f"'{name}'" in sources, (
                f"{name} is documented in .env.example but nothing under app/ "
                "reads it")
