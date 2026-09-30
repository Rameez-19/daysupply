"""The capture loop, closed — and the retry that keeps it closed under load.

Two things were broken and both were invisible from the dashboard:

* An extraction could be perfectly correct and never reach the ledger, so
  `captures_today` read 0 forever. The product's whole thesis is capture
  flowing upward into the supply chain; until the write-through existed, it
  did not flow.
* A transient 503 from a busy Flash model surfaced a raw API status to the
  health worker and lost the recording.

These tests use fakes rather than calling Gemini or BigQuery, so they run in
the suite without a key, a network or a bill.
"""

import re
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import capture  # noqa: E402
from app import capture_pipeline  # noqa: E402


class _Boom(Exception):
    """Stands in for an SDK error carrying an HTTP status."""

    def __init__(self, code: int, message: str):
        super().__init__(f"{code} {message}")
        self.code = code


class _FakeModels:
    """Fails a scripted number of times, then succeeds."""

    def __init__(self, failures: int, exc: Exception, reply: str = "[]"):
        self.remaining = failures
        self.exc = exc
        self.reply = reply
        self.calls: list[str] = []
        self.configs: list[object] = []

    def generate_content(self, model, contents, config=None):
        self.calls.append(model)
        self.configs.append(config)
        if self.remaining > 0:
            self.remaining -= 1
            raise self.exc
        return type("R", (), {"text": self.reply})()


class _FakeClient:
    def __init__(self, models):
        self.models = models


@pytest.fixture
def fast_backoff(monkeypatch):
    """Keep the tests quick without disabling the backoff logic itself."""
    monkeypatch.setattr(capture, "BACKOFF_BASE_SECONDS", 0.001)
    monkeypatch.setattr(capture, "BACKOFF_CAP_SECONDS", 0.005)


def _install(monkeypatch, models):
    monkeypatch.setattr(capture, "_get_client", lambda *a, **k: _FakeClient(models))


class TestRetryOn503:
    def test_the_rules_travel_as_a_system_instruction(self, monkeypatch,
                                                      fast_backoff):
        """The prompt is configuration, not the first turn of the conversation.

        It also has to reach the model on *every* attempt, including the ones
        that fall back to the cheaper model — a retry that quietly dropped the
        extraction rules would return plausible, differently-shaped JSON.
        """
        models = _FakeModels(failures=2, exc=_Boom(503, "UNAVAILABLE"),
                             reply="[]")
        _install(monkeypatch, models)
        capture.process_text("kuch bhi")
        assert len(models.configs) == 3
        for config in models.configs:
            assert config is not None
            assert "VAGUE QUANTITIES" in config.system_instruction

    def test_vague_quantity_rules_are_in_the_prompt(self):
        """The 'teen char' gap: a range must be treated like 'aadha dabba'."""
        for phrase in ("teen char", "do teen", "lagbhag", "aas paas", "kuch"):
            assert phrase in capture.SYSTEM_PROMPT, phrase
        assert "confidence <= 0.5" in capture.SYSTEM_PROMPT

    def test_a_transient_503_is_retried_and_succeeds(self, monkeypatch,
                                                     fast_backoff):
        models = _FakeModels(
            failures=1,
            exc=_Boom(503, "UNAVAILABLE. This model is currently "
                           "experiencing high demand."),
            reply='[{"local_name":"paracetamol","quantity":10}]')
        _install(monkeypatch, models)
        assert "paracetamol" in capture.process_text("kuch bhi")
        assert len(models.calls) == 2, "should have retried exactly once"

    def test_it_falls_back_to_the_cheaper_model_under_sustained_load(
            self, monkeypatch, fast_backoff):
        """A congested model is better answered by a different model."""
        models = _FakeModels(
            failures=capture.FALLBACK_AFTER_ATTEMPTS,
            exc=_Boom(503, "UNAVAILABLE high demand"),
            reply="[]")
        _install(monkeypatch, models)
        capture.process_text("kuch bhi")
        assert models.calls[0] == capture.MODEL
        assert models.calls[-1] == capture.split_model(capture.FALLBACK_MODEL)[0], (
            f"expected a fallback to {capture.FALLBACK_MODEL}, "
            f"got {models.calls}")

    def test_total_failure_gives_the_worker_a_sentence_not_a_status_code(
            self, monkeypatch, fast_backoff):
        """The forced-failure case. Never a raw API error, never silence."""
        models = _FakeModels(failures=99,
                             exc=_Boom(503, "UNAVAILABLE high demand"))
        _install(monkeypatch, models)

        with pytest.raises(capture.ModelUnavailable) as caught:
            capture.process_text("kuch bhi")
        message = str(caught.value)
        assert "503" not in message and "UNAVAILABLE" not in message
        assert "not been lost" in message
        assert len(models.calls) == capture.MAX_ATTEMPTS

    def test_the_handler_surfaces_it_as_retryable_and_keeps_the_transcript(
            self, monkeypatch, fast_backoff):
        models = _FakeModels(failures=99,
                             exc=_Boom(503, "UNAVAILABLE high demand"))
        _install(monkeypatch, models)

        result = capture.handle_chat("paracetamol ke do sau tablet", "IN-155740")
        assert result["retryable"] is True
        assert result["attempts"] == capture.MAX_ATTEMPTS
        assert "503" not in result["error"]
        assert "503" in result["technical_detail"], (
            "the raw status must still be available to us, just not to the "
            "health worker")
        assert result["raw_transcript"] == "paracetamol ke do sau tablet", (
            "the typed message must survive a model failure")

    def test_a_non_retryable_error_is_not_retried(self, monkeypatch,
                                                  fast_backoff):
        """A 400 will fail identically four times; retrying wastes the worker's
        time and hides the real problem."""
        models = _FakeModels(failures=99, exc=_Boom(400, "INVALID_ARGUMENT"))
        _install(monkeypatch, models)
        with pytest.raises(_Boom):
            capture.process_text("kuch bhi")
        assert len(models.calls) == 1

    def test_backoff_actually_waits(self, monkeypatch):
        """Retrying instantly four times is not a retry policy."""
        monkeypatch.setattr(capture, "BACKOFF_BASE_SECONDS", 0.05)
        monkeypatch.setattr(capture, "BACKOFF_CAP_SECONDS", 1.0)
        models = _FakeModels(failures=2, exc=_Boom(503, "UNAVAILABLE"),
                             reply="[]")
        _install(monkeypatch, models)
        started = time.monotonic()
        capture.process_text("kuch bhi")
        assert time.monotonic() - started >= 0.05


class TestLedgerProjection:
    def test_only_schema_columns_are_written(self):
        """Capture records carry fields the ledger has no column for."""
        record = {
            "event_id": "e1", "resource_type": "medicine",
            "facility_id": "IN-1", "item_id": "PARACETAMOL",
            "event_type": "received", "quantity": 200,
            "event_ts": "2026-09-02T00:00:00+00:00", "source": "chat",
            "confidence": 0.95, "raw_transcript": "…",
            "expiry_date": None, "resource_subtype": None, "capacity": None,
            # Not ledger columns:
            "local_name": "paracetamol", "unit": "tablet",
            "review_reason": "should not be written",
        }
        row = capture_pipeline._ledger_row(record)
        assert set(row) == set(capture_pipeline.LEDGER_COLUMNS)
        for absent in ("local_name", "unit", "review_reason"):
            assert absent not in row

    def test_an_empty_write_is_not_an_error(self):
        written, error = capture_pipeline.write_to_ledger([])
        assert written == 0 and error is None


class TestTheGate:
    """Above the gate writes through; below it waits for a human."""

    def test_high_confidence_goes_to_events_not_review(self):
        result = capture_pipeline.route(
            [{"local_name": "paracetamol", "confidence": 0.95,
              "quantity": 200, "event_type": "received"}],
            "IN-155740", "chat")
        assert len(result["events"]) == 1
        assert not result["review_queue"]

    def test_low_confidence_waits_for_a_human(self):
        result = capture_pipeline.route(
            [{"local_name": "paracetamol", "confidence": 0.3,
              "quantity": 200, "event_type": "received"}],
            "IN-155740", "chat")
        assert not result["events"]
        assert len(result["review_queue"]) == 1

    def test_an_unmatched_item_can_never_be_approved_into_the_ledger(self):
        """Approval promotes a record; it must not invent an item_id."""
        result = capture_pipeline.route(
            [{"local_name": "wo cheez", "confidence": 0.99, "quantity": 3}],
            "IN-155740", "chat")
        assert len(result["review_queue"]) == 1
        assert result["review_queue"][0]["item_id"] is None


class _FakeDoc:
    def __init__(self, data):
        self._data = data
        self.written = None
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data)

    def get(self):
        return self

    def set(self, data):
        self.written = data


class _FakeFirestore:
    def __init__(self, doc):
        self.doc = doc

    def collection(self, _name):
        return self

    def document(self, _id):
        return self.doc


class TestApprovalMustProduceAUsableRow:
    """A stock event with no quantity records no stock movement.

    Approving one inflates the capture count while telling the supply chain
    nothing. An earlier version of `approve_review_item` did not check, and
    wrote exactly such a row into `resource_events` during live testing.
    """

    def _approve(self, monkeypatch, record, quantity=None, writes=None):
        doc = _FakeDoc(record)
        fake_db = _FakeFirestore(doc)
        monkeypatch.setattr(
            "google.cloud.firestore.Client", lambda **kw: fake_db)
        monkeypatch.setattr(
            capture_pipeline, "write_to_ledger",
            lambda records: (writes.append(records) or (len(records), None))
            if writes is not None else (len(records), None))
        return capture_pipeline.approve_review_item("e1", quantity), doc

    def test_approval_without_a_quantity_is_refused(self, monkeypatch):
        result, doc = self._approve(
            monkeypatch,
            {"event_id": "e1", "item_id": "ORAL-REHYDRATION-SALTS",
             "quantity": None, "status": "pending"})
        assert result["approved"] is False
        assert result["needs_quantity"] is True
        assert doc.written is None, "nothing may be marked approved"

    def test_a_reviewer_supplied_quantity_is_what_gets_written(self,
                                                              monkeypatch):
        writes: list = []
        result, doc = self._approve(
            monkeypatch,
            {"event_id": "e1", "item_id": "ORAL-REHYDRATION-SALTS",
             "quantity": None, "status": "pending"},
            quantity=12, writes=writes)
        assert result["approved"] is True
        assert result["quantity"] == 12
        assert writes[0][0]["quantity"] == 12
        assert doc.written["approved_quantity_source"] == "reviewer"

    def test_an_extracted_quantity_is_kept_when_no_override_is_given(
            self, monkeypatch):
        result, doc = self._approve(
            monkeypatch,
            {"event_id": "e1", "item_id": "PARACETAMOL", "quantity": 200,
             "status": "pending"})
        assert result["approved"] is True and result["quantity"] == 200
        assert doc.written["approved_quantity_source"] == "extraction"

    def test_an_unmatched_item_is_refused(self, monkeypatch):
        result, doc = self._approve(
            monkeypatch,
            {"event_id": "e1", "item_id": None, "quantity": 5,
             "status": "pending"})
        assert result["approved"] is False
        assert "never matched" in result["reason"]
        assert doc.written is None

    def test_double_approval_is_refused(self, monkeypatch):
        result, _ = self._approve(
            monkeypatch,
            {"event_id": "e1", "item_id": "PARACETAMOL", "quantity": 5,
             "status": "approved"})
        assert result["approved"] is False
        assert result["reason"] == "already approved"

    def test_a_negative_quantity_is_refused(self, monkeypatch):
        result, _ = self._approve(
            monkeypatch,
            {"event_id": "e1", "item_id": "PARACETAMOL", "quantity": None,
             "status": "pending"},
            quantity=-4)
        assert result["approved"] is False
        assert "negative" in result["reason"]


class TestLossesAndAdjustments:
    """One of the three core LMIS data items, and it was missing.

    Stock on hand and consumption were both recorded; losses were not. A supply
    chain that cannot see breakage, spoilage and theft cannot explain its own
    shortfalls — it shows stock that should be there and is not, with no reason
    attached.
    """

    def test_lost_is_an_accepted_event_type(self):
        assert "lost" in capture_pipeline.EVENT_TYPES

    def test_a_loss_routes_like_any_other_capture(self):
        result = capture_pipeline.route(
            [{"local_name": "paracetamol", "confidence": 0.95, "quantity": 10,
              "event_type": "lost", "loss_reason": "broken"}],
            "IN-155740", "voice")
        assert len(result["events"]) == 1
        event = result["events"][0]
        assert event["event_type"] == "lost"
        assert event["resource_subtype"] == "broken"
        assert event["item_id"] == "PARACETAMOL"

    def test_a_loss_below_the_gate_still_waits_for_a_human(self):
        result = capture_pipeline.route(
            [{"local_name": "paracetamol", "confidence": 0.3, "quantity": 10,
              "event_type": "lost", "loss_reason": "stolen"}],
            "IN-155740", "voice")
        assert not result["events"]
        assert len(result["review_queue"]) == 1

    def test_an_unstated_reason_becomes_unknown_not_a_guess(self):
        """"It's gone and I don't know why" is a real and common answer."""
        assert capture_pipeline.normalise_loss_reason("lost", None) == "unknown"
        assert capture_pipeline.normalise_loss_reason("lost", "") == "unknown"

    def test_an_unfamiliar_reason_is_kept_verbatim(self):
        """The categories are a starting point, not a closed vocabulary.

        Discarding a word we do not recognise would destroy the evidence for
        widening them.
        """
        assert capture_pipeline.normalise_loss_reason(
            "lost", "Rats") == "rats"

    def test_a_reason_on_a_receipt_is_dropped(self):
        assert capture_pipeline.normalise_loss_reason("received", "broken") is None

    def test_losses_are_netted_out_of_on_hand(self):
        """A broken vial is off the shelf whether or not anyone said why."""
        from ingestion import build_current_stock
        assert "lost" in build_current_stock.CONSUMING_EVENT_TYPES


class TestEventTypeIsValidated:
    """The event type used to pass through unchecked, model to ledger.

    A single hallucinated word — "issued", "consumed" — would write an event
    type the balance arithmetic nets neither in nor out. Stock would quietly
    stop adding up and nothing would say why. That is the most dangerous kind
    of failure this system can have, because every downstream figure stays
    plausible.
    """

    def test_an_unknown_event_type_goes_to_review_not_the_ledger(self):
        result = capture_pipeline.route(
            [{"local_name": "paracetamol", "confidence": 0.99, "quantity": 10,
              "event_type": "issued"}],
            "IN-155740", "voice")
        assert not result["events"]
        assert len(result["review_queue"]) == 1
        assert "issued" in result["review_queue"][0]["review_reason"]

    def test_every_accepted_type_is_netted_or_added(self):
        """No accepted type may be invisible to the balance arithmetic."""
        from ingestion import build_current_stock
        consuming = set(build_current_stock.CONSUMING_EVENT_TYPES)
        adding = {"received"}
        # `count` is a stocktake, deliberately neither — see HANDOVER §9f.
        neutral = {"count"}
        assert capture_pipeline.EVENT_TYPES == consuming | adding | neutral



class TestModelChain:
    """The primary, then each fallback in turn; a retired model is skipped."""

    def test_the_chain_is_walked_in_order(self, monkeypatch, fast_backoff):
        models = _FakeModels(failures=99, exc=_Boom(503, "UNAVAILABLE high demand"))
        _install(monkeypatch, models)
        with pytest.raises(capture.ModelUnavailable):
            capture.process_text("kuch bhi")
        expected = ([capture.MODEL] * capture.FALLBACK_AFTER_ATTEMPTS
                    + [capture.split_model(m)[0] for m in capture.FALLBACK_MODELS])
        assert models.calls == expected[:capture.MAX_ATTEMPTS]

    def test_a_retired_model_is_skipped_without_failing_the_request(
            self, monkeypatch, fast_backoff):
        class Retired(_FakeModels):
            def generate_content(self, model, contents, config=None):
                self.calls.append(model)
                if model == capture.MODEL:
                    raise _Boom(404, "NOT_FOUND. This model is no longer available")
                return type("R", (), {"text": "[]"})()
        models = Retired(failures=0, exc=None)
        _install(monkeypatch, models)
        assert capture.process_text("kuch bhi") == "[]"
        assert models.calls == [capture.MODEL, capture.split_model(capture.FALLBACK_MODELS[0])[0]], (
            "a 404 must move to the next model at once, not retry the dead one")

    def test_no_retired_model_is_configured(self):
        """gemini-1.5-pro was shut down. gemini-2.5-flash is closed to new AI
        Studio users but still served on Vertex AI, which is the backend."""
        chain = [capture.MODEL] + [capture.split_model(m)[0] for m in capture.FALLBACK_MODELS]
        assert "gemini-1.5-pro" not in chain
        assert capture.BACKEND == "vertex"

    def test_the_chain_runs_newest_flash_first(self):
        """Newest to oldest, from prompts/models.json."""
        chain = [capture.MODEL] + [capture.split_model(m)[0] for m in capture.FALLBACK_MODELS]
        versions = [float(re.search(r"gemini-(\d+(?:\.\d+)?)-flash", m).group(1)) for m in chain]
        assert versions == sorted(versions, reverse=True), chain
        assert chain[0] == "gemini-3.8-flash"

    def test_the_mumbai_models_run_in_mumbai(self):
        """Where Vertex AI serves a model in asia-south1, it is used there."""
        for m in capture.FALLBACK_MODELS:
            name, loc = capture.split_model(m)
            if name in ("gemini-3.5-flash", "gemini-2.5-flash"):
                assert loc == "asia-south1", m

    def test_the_prompts_are_files_in_the_repository(self):
        for name in ("extraction_system.txt", "chat_instruction.txt",
                     "photo_instruction.txt", "escalation_note_system.txt", "models.json"):
            assert (capture.PROMPTS_DIR / name).exists(), name
        assert capture.SYSTEM_PROMPT == capture.load_prompt("extraction_system.txt")

    def test_names_come_back_in_latin_letters(self):
        """The catalogue matcher knows Latin and Devanagari spellings only, so
        a Telugu-script name would never match and every Telugu report would
        be held for review."""
        assert "English (Latin) letters" in capture.SYSTEM_PROMPT
