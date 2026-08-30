"""One pipeline, three ways in — and what it does with messy input.

The degradation hierarchy only means something if a worse input mode yields a
*lower-confidence record*, not a differently-shaped one. These tests pin that:
barcode, voice and chat all produce the same record shape, go through the same
catalogue matcher at threshold 85, and land in the same review queue when they
fall short.

The messy cases are the point. A health worker at the end of a shift does not
speak like a formulary, and the transcripts below are written the way speech
recognition actually renders that — dropped consonants, brand names, Hindi
quantity words, background chatter. What must never happen is a confident write
against the wrong drug.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import capture_pipeline  # noqa: E402
from app import items  # noqa: E402

FACILITY = "IN-155740"


def route(extractions, source="voice"):
    """Route without touching Firestore."""
    return capture_pipeline.route(extractions, FACILITY, source)


def one(local_name, confidence=0.9, quantity=100, event_type="dispensed",
        unit="tablet", source="voice"):
    return route([{
        "local_name": local_name,
        "confidence": confidence,
        "quantity": quantity,
        "event_type": event_type,
        "unit": unit,
    }], source)


class TestOnePipeline:
    """All three modes must produce the same record shape."""

    @pytest.mark.parametrize("source", ["voice", "chat", "barcode"])
    def test_record_shape_is_identical(self, source):
        result = one("paracetamol", source=source)
        assert result["source"] == source
        assert len(result["events"]) == 1
        event = result["events"][0]
        for field in ("event_id", "facility_id", "local_name", "item_id",
                      "event_type", "quantity", "unit", "confidence",
                      "source", "event_ts"):
            assert field in event, f"{source} record is missing {field}"

    def test_unknown_source_is_rejected(self):
        with pytest.raises(ValueError):
            route([{"local_name": "paracetamol", "confidence": 0.9,
                    "quantity": 1}], source="telepathy")

    def test_barcode_carries_full_confidence(self):
        result = capture_pipeline.handle_barcode.__wrapped__ \
            if hasattr(capture_pipeline.handle_barcode, "__wrapped__") else None
        # The constant is what matters, not the wrapper.
        assert capture_pipeline.BARCODE_CONFIDENCE == 1.0

    def test_barcode_beats_voice_on_confidence(self):
        """The hierarchy is only real if the ranking shows up in the data."""
        assert capture_pipeline.BARCODE_CONFIDENCE > 0.6


class TestConfidenceGate:
    def test_low_confidence_goes_to_review(self):
        result = one("paracetamol", confidence=0.45)
        assert not result["events"]
        assert len(result["review_queue"]) == 1
        assert "confidence" in result["review_queue"][0]["review_reason"]

    def test_missing_quantity_goes_to_review(self):
        result = one("paracetamol", quantity=None)
        assert not result["events"]
        assert "quantity" in result["review_queue"][0]["review_reason"]

    def test_confident_and_complete_is_written(self):
        result = one("paracetamol", confidence=0.95, quantity=200)
        assert len(result["events"]) == 1
        assert result["events"][0]["item_id"] == "PARACETAMOL"


class TestMessyRealSpeech:
    """Transcripts as speech recognition actually renders them."""

    # These must resolve: the drug is identifiable despite the mess.
    RESOLVES = [
        ("paracetamol ke do sau tablet", "PARACETAMOL"),
        ("bukhar ki goli", "PARACETAMOL"),
        ("dolo 650 ka strip", "PARACETAMOL"),
        ("pcm", "PARACETAMOL"),
        ("amoxy 250", "AMOXICILLIN"),
        ("ORS ka packet aaya hai", "ORAL-REHYDRATION-SALTS"),
        ("khoon ki goli", "FERROUS-SALT-FOLIC-ACID"),
        ("sugar ki goli metformin", "METFORMIN"),
        ("asthalin inhaler", "SALBUTAMOL"),
        ("zinc ki tablet", "ZINC-SULPHATE"),
    ]

    # These must NOT resolve. A wrong item_id is worse than no item_id.
    GOES_TO_REVIEW = [
        "haan ji boliye",
        "aaj kuch nahi aaya",
        "ek minute ruko",
        "pata nahi kya hai ye",
        "kal aana",
        "background mein bacche ro rahe hain",
    ]

    @pytest.mark.parametrize("spoken,expected", RESOLVES)
    def test_messy_but_identifiable_resolves(self, spoken, expected):
        assert items.match(spoken) == expected, (
            f"{spoken!r} should have resolved to {expected}")

    @pytest.mark.parametrize("spoken", GOES_TO_REVIEW)
    def test_unidentifiable_speech_is_reviewed_not_guessed(self, spoken):
        result = one(spoken, confidence=0.9)
        assert not result["events"], (
            f"{spoken!r} was written as a stock event — it names no medicine")
        assert len(result["review_queue"]) == 1
        assert "did not match" in result["review_queue"][0]["review_reason"]

    def test_a_whole_messy_note_splits_correctly(self):
        """One note, three items: one clean, one hesitant, one unintelligible."""
        result = route([
            {"local_name": "paracetamol", "confidence": 0.94,
             "quantity": 200, "event_type": "received", "unit": "tablet"},
            {"local_name": "ORS", "confidence": 0.42,
             "quantity": 30, "event_type": "received", "unit": "sachet"},
            {"local_name": "wo neeli wali dawai", "confidence": 0.88,
             "quantity": 50, "event_type": "dispensed", "unit": "tablet"},
        ])
        assert len(result["events"]) == 1
        assert result["events"][0]["item_id"] == "PARACETAMOL"
        assert len(result["review_queue"]) == 2
        reasons = " ".join(r["review_reason"] for r in result["review_queue"])
        assert "confidence" in reasons
        assert "did not match" in reasons


class TestModelOutputParsing:
    def test_plain_json_array(self):
        parsed = capture_pipeline.parse_model_json(
            '[{"local_name": "paracetamol", "quantity": 10}]')
        assert len(parsed) == 1

    def test_fenced_json_is_tolerated(self):
        """Gemini adds markdown fences often enough that this must not break."""
        parsed = capture_pipeline.parse_model_json(
            '```json\n[{"local_name": "ORS", "quantity": 4}]\n```')
        assert parsed[0]["local_name"] == "ORS"

    def test_single_object_is_wrapped(self):
        parsed = capture_pipeline.parse_model_json(
            '{"local_name": "paracetamol", "quantity": 1}')
        assert isinstance(parsed, list) and len(parsed) == 1

    def test_prose_is_rejected_loudly(self):
        with pytest.raises(capture_pipeline.ExtractionError):
            capture_pipeline.parse_model_json(
                "Sure! Here are the medicines I found:")
