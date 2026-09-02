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
    monkeypatch.setattr(capture, "_get_client", lambda: _FakeClient(models))


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
        assert models.calls[-1] == capture.FALLBACK_MODEL, (
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
