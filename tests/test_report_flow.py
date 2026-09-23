"""The Report page's contract with the pipeline: preview, then confirm.

A health worker hears a read-back and says yes before anything is written.
These tests pin the two halves of that — `preview()` never persists, and
`confirm()` writes through the same gate every other source uses — plus the
three new ways in (tap, photo, sms). They use fakes for the catalogue and
the stores, so they run without BigQuery, Firestore or Gemini.
"""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import capture, capture_pipeline, items  # noqa: E402

FACILITY = "IN-155740"

CATALOGUE = {
    "PARACETAMOL": "Paracetamol",
    "METFORMIN": "Metformin",
    "ORAL-REHYDRATION-SALTS": "Oral rehydration salts",
}


@pytest.fixture(autouse=True)
def fake_catalogue(monkeypatch):
    """A three-item catalogue; matching is by lowercase display name."""
    monkeypatch.setattr(items, "known", lambda i: i in CATALOGUE)
    monkeypatch.setattr(items, "display_name", lambda i: CATALOGUE.get(i))

    def match(name):
        key = (name or "").lower()
        for item_id, display in CATALOGUE.items():
            if display.lower() in key or key in display.lower() and key:
                return item_id
        return None
    monkeypatch.setattr(items, "match", match)


@pytest.fixture
def stores(monkeypatch):
    """Record what would be persisted instead of persisting it."""
    written = {"ledger": [], "persist_calls": 0}

    def fake_persist(result):
        written["persist_calls"] += 1
        written["ledger"].extend(result.get("events", []))
        result["written_to_ledger"] = len(result.get("events", []))
        result["persisted"] = True
        return result
    monkeypatch.setattr(capture_pipeline, "persist", fake_persist)
    return written


class TestPreviewNeverWrites:
    def test_preview_returns_rows_and_touches_nothing(self, stores):
        out = capture_pipeline.preview(
            [{"local_name": "paracetamol", "event_type": "received",
              "quantity": 200, "unit": "tablet", "confidence": 0.95}],
            FACILITY, "voice", raw_transcript="paracetamol 200 aaye")
        assert out["preview"] is True
        assert out["persisted"] is False
        assert stores["persist_calls"] == 0
        assert out["events"][0]["item_name"] == "Paracetamol"

    def test_preview_shows_what_would_be_held_and_why(self, stores):
        out = capture_pipeline.preview(
            [{"local_name": "paracetamol", "event_type": "received",
              "quantity": None, "unit": "tablet", "confidence": 0.95}],
            FACILITY, "voice")
        assert not out["events"]
        assert out["review_queue"][0]["review_reason"] == "no quantity was stated"


class TestConfirmWritesThroughTheGate:
    def test_a_tapped_tile_is_written_at_full_confidence(self, stores):
        out = capture_pipeline.confirm(
            [{"item_id": "PARACETAMOL", "local_name": "Paracetamol",
              "event_type": "received", "quantity": 200, "unit": "tablet"}],
            FACILITY, "tap")
        assert stores["persist_calls"] == 1
        row = stores["ledger"][0]
        assert row["item_id"] == "PARACETAMOL"
        assert row["confidence"] == capture_pipeline.CONFIRMED_CONFIDENCE
        assert row["source"] == "tap"
        assert out["confirmed_by"] == "health worker"

    def test_a_client_supplied_id_is_verified_not_trusted(self, stores):
        """An id that is not in the catalogue falls back to name matching,
        and a name that matches nothing is held — never written as the
        invented id."""
        out = capture_pipeline.confirm(
            [{"item_id": "HALLUCINATED-CODE", "local_name": "wo neeli goli",
              "event_type": "received", "quantity": 5, "unit": "strip"}],
            FACILITY, "tap")
        assert not out["events"]
        held = out["review_queue"][0]
        assert held["item_id"] is None
        assert "did not match" in held["review_reason"]

    def test_confirming_cannot_skip_the_quantity_rule(self, stores):
        out = capture_pipeline.confirm(
            [{"item_id": "METFORMIN", "local_name": "Metformin",
              "event_type": "dispensed", "quantity": None, "unit": "tablet"}],
            FACILITY, "photo")
        assert not out["events"]
        assert out["review_queue"][0]["review_reason"] == "no quantity was stated"

    def test_confirming_cannot_skip_the_event_type_rule(self, stores):
        out = capture_pipeline.confirm(
            [{"item_id": "METFORMIN", "local_name": "Metformin",
              "event_type": "issued", "quantity": 10, "unit": "tablet"}],
            FACILITY, "tap")
        assert not out["events"]
        assert "not a stock movement" in out["review_queue"][0]["review_reason"]

    def test_a_loss_keeps_its_reason(self, stores):
        capture_pipeline.confirm(
            [{"item_id": "PARACETAMOL", "local_name": "Paracetamol",
              "event_type": "lost", "quantity": 12, "unit": "strip",
              "loss_reason": "expired"}],
            FACILITY, "tap")
        assert stores["ledger"][0]["resource_subtype"] == "expired"

    def test_staff_on_duty_goes_through_as_personnel(self, stores):
        capture_pipeline.confirm(
            [{"local_name": "nurse", "event_type": "count", "quantity": 2,
              "unit": "person"}],
            FACILITY, "tap", resource_type="personnel")
        row = stores["ledger"][0]
        assert row["resource_type"] == "personnel"
        assert row["item_id"] == "STAFF-NURSE"

    def test_unknown_source_is_refused(self, stores):
        with pytest.raises(ValueError):
            capture_pipeline.confirm([], FACILITY, "carrier-pigeon")

    def test_every_new_source_is_in_the_shared_list(self):
        for source in ("tap", "photo", "sms"):
            assert source in capture_pipeline.SOURCES


class _Reply:
    def __init__(self, text):
        self.text = text


class _Models:
    def __init__(self, reply):
        self.reply = reply
        self.contents = []

    def generate_content(self, model, contents, config=None):
        self.contents.append(contents)
        return _Reply(self.reply)


@pytest.fixture
def gemini(monkeypatch):
    models = _Models('[{"local_name": "paracetamol", "event_type": "received",'
                     ' "quantity": 200, "unit": "tablet", "confidence": 0.9}]')
    monkeypatch.setattr(capture, "_get_client",
                        lambda: type("C", (), {"models": models})())
    return models


class TestPhotoIsAlwaysAPreview:
    def test_a_register_photo_never_writes(self, gemini, stores):
        out = capture.handle_photo(b"\x89PNG fake", FACILITY, "image/png")
        assert out["source"] == "photo"
        assert out["preview"] is True
        assert stores["persist_calls"] == 0
        assert out["events"][0]["item_name"] == "Paracetamol"

    def test_the_image_travels_with_the_register_instruction(self, gemini):
        capture.handle_photo(b"\x89PNG fake", FACILITY, "image/png")
        contents = gemini.contents[0]
        assert contents[0] == capture.PHOTO_INSTRUCTION
        assert "stock register" in capture.PHOTO_INSTRUCTION
        assert "Do not invent rows" in capture.PHOTO_INSTRUCTION


class TestVoiceAndChatPreview:
    def test_voice_preview_writes_nothing(self, gemini, stores):
        out = capture.handle_capture(b"audio", FACILITY, "audio/webm",
                                     preview=True)
        assert out["preview"] is True and stores["persist_calls"] == 0

    def test_voice_without_preview_still_writes(self, gemini, stores):
        """The offline queue syncs with nobody holding the phone."""
        out = capture.handle_capture(b"audio", FACILITY, "audio/webm")
        assert stores["persist_calls"] == 1
        assert out["events"][0]["item_name"] == "Paracetamol"

    def test_chat_preview_writes_nothing(self, gemini, stores):
        out = capture.handle_chat("paracetamol 200 aaye", FACILITY,
                                  preview=True)
        assert out["preview"] is True and stores["persist_calls"] == 0


class TestSms:
    def test_the_message_must_name_the_centre(self, gemini, stores):
        out = capture.handle_sms("+91xxxx", "paracetamol 200 aaye")
        assert out["error"] == "no facility id"
        assert "IN-155740" in out["reply"]
        assert stores["persist_calls"] == 0

    def test_a_well_formed_text_is_recorded_and_answered(self, gemini, stores):
        out = capture.handle_sms("+91xxxx", "in-155740 paracetamol 200 aaye")
        assert out["source"] == "sms"
        assert out["sender"] == "+91xxxx"
        assert stores["ledger"][0]["facility_id"] == "IN-155740"
        assert out["reply"] == "OK Paracetamol 200 tablet received"

    def test_a_held_row_is_answered_as_held(self, monkeypatch, stores):
        models = _Models('[{"local_name": "paracetamol", "event_type": '
                         '"received", "quantity": null, "unit": "tablet", '
                         '"confidence": 0.9}]')
        monkeypatch.setattr(capture, "_get_client",
                            lambda: type("C", (), {"models": models})())
        out = capture.handle_sms("", "IN-155740 paracetamol kuch aaye")
        assert out["reply"].startswith("HELD Paracetamol: no quantity")


class TestNoInventedReviewExamples:
    def test_the_demo_module_is_gone(self):
        assert not (ROOT / "app" / "demo_data.py").exists()
        src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
        assert "demo_data" not in src
        assert "is_example" not in src.replace('"is_example_data": False', "")


WEB = ROOT / "web"


class TestTheReportPageStrings:
    """Every language carries every key, and every key the code asks for
    exists: a missing string would silently show its key to a health worker.
    """

    LANGS = ("en", "hi", "mr", "te", "bn")

    def _strings(self):
        src = (WEB / "report.js").read_text(encoding="utf-8")
        block = src[src.index("const REPORT_STRINGS"):src.index("\nlet reportLang")]
        key = re.compile(r"'([a-z]+(?:\.[a-z]+)*)':")
        tables = {}
        for i, lang in enumerate(self.LANGS):
            start = block.index(f"  {lang}: {{")
            later = [block.index(f"  {l}: {{") for l in self.LANGS
                     if block.index(f"  {l}: {{") > start]
            end = min(later) if later else len(block)
            tables[lang] = set(key.findall(block[start:end]))
        return src, tables

    def test_every_language_carries_the_same_keys(self):
        _, tables = self._strings()
        en = tables["en"]
        for lang, keys in tables.items():
            assert keys == en, (lang, sorted(en - keys), sorted(keys - en))

    def test_every_language_is_offered_in_the_picker(self):
        src, tables = self._strings()
        for lang in tables:
            assert f"['{lang}'," in src, lang

    def test_every_language_is_written_in_its_own_script(self):
        """A dictionary pasted in English under a Telugu key would pass the
        key check; this catches it."""
        src, _ = self._strings()
        scripts = {"hi": "\u0900-\u097F", "mr": "\u0900-\u097F",
                   "te": "\u0C00-\u0C7F", "bn": "\u0980-\u09FF"}
        block = src[src.index("const REPORT_STRINGS"):src.index("\nlet reportLang")]
        for lang, rng in scripts.items():
            start = block.index(f"  {lang}: {{")
            body = block[start:start + 4000]
            title = re.search(r"'report\.title': '([^']+)'", body).group(1)
            assert re.search(f"[{rng}]", title), (lang, title)

    def test_every_key_the_code_uses_exists(self):
        src, tables = self._strings()
        en = tables["en"]
        used = set(re.findall(r"\bt\('([a-z.]+)'\)", src))
        html = (WEB / "index.html").read_text(encoding="utf-8")
        used |= set(re.findall(r'data-i18n="([a-z.]+)"', html))
        for prefix, values in (("ev.", ("received", "dispensed", "count", "lost")),
                               ("evs.", sorted(capture_pipeline.EVENT_TYPES)),
                               ("loss.", sorted(capture_pipeline.LOSS_REASONS)),
                               ("unit.", ("tablet", "capsule", "vial", "bottle",
                                          "strip", "unit", "unknown", "person", "bed")),
                               ("mode.", ("tap", "voice", "photo", "scan",
                                          "chat", "staff", "beds"))):
            used |= {prefix + v for v in values}
        missing = sorted(used - en)
        assert not missing, missing

    def test_the_drafted_note_speaks_every_page_language(self):
        from app import brief
        _, tables = self._strings()
        assert set(tables) <= set(brief.LANGUAGES)

    def test_the_page_no_longer_posts_against_a_hardcoded_centre(self):
        app = (WEB / "app.js").read_text(encoding="utf-8")
        assert "IN-101234" not in app
        assert "'IN-155740'" not in app

    def test_report_js_is_loaded_and_cached(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        sw = (WEB / "sw.js").read_text(encoding="utf-8")
        assert '<script src="report.js">' in html
        assert "'/report.js'" in sw
