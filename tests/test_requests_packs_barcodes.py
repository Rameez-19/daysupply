"""Three things a health worker does that are not a stock movement on their own.

- "Paracetamol ke 100 tablet chahiye" is a request. It used to come back as
  "nothing was recognised", which made the app sound broken.
- A photo of a medicine pack names a medicine but says nothing about what
  happened to it. It used to come back empty.
- A pack's barcode names a product the catalogue has no code for. It used to
  go to review every time; now the worker says once which medicine it is.

None of these may write a row to the ledger by itself.
"""

import pytest

from app import capture
from app import capture_pipeline as cp

CENTRE = "IN-19662"


class TestARequestIsNotAMovement:
    def test_a_request_is_returned_and_never_written(self):
        r = cp.preview([{"local_name": "paracetamol", "event_type": "request",
                         "quantity": 100, "unit": "tablet", "confidence": 0.95}],
                       CENTRE, "chat")
        assert r["events"] == [] and r["review_queue"] == []
        req = r["requests"]
        assert len(req) == 1
        assert req[0]["item_id"] == "PARACETAMOL" and req[0]["quantity"] == 100
        assert req[0]["item_name"]

    def test_a_report_with_a_request_keeps_its_movement(self):
        r = cp.preview([
            {"local_name": "ors", "event_type": "received", "quantity": 50,
             "unit": "unknown", "confidence": 0.95},
            {"local_name": "paracetamol", "event_type": "request",
             "quantity": 100, "unit": "tablet", "confidence": 0.95}],
            CENTRE, "voice")
        assert [e["item_id"] for e in r["events"]] == ["ORAL-REHYDRATION-SALTS"]
        assert [q["item_id"] for q in r["requests"]] == ["PARACETAMOL"]

    def test_the_prompt_says_a_request_is_not_a_receipt(self):
        assert '"request"' in capture.SYSTEM_PROMPT
        assert "chahiye" in capture.SYSTEM_PROMPT


class TestAPackPhotoNamesTheMedicine:
    def test_an_identified_pack_writes_nothing(self):
        r = cp.preview([{"local_name": "Paracetamol Tablets IP 500 mg",
                         "generic_name": "paracetamol", "event_type": "identify",
                         "quantity": None, "unit": "tablet", "confidence": 0.9}],
                       CENTRE, "photo")
        assert r["events"] == [] and r["review_queue"] == []
        assert [i["item_id"] for i in r["identified"]] == ["PARACETAMOL"]

    def test_the_photo_instruction_handles_a_pack(self):
        assert '"identify"' in capture.PHOTO_INSTRUCTION


class _Snap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data or {})


class _Docs:
    """A Firestore stand-in: collection(name).document(id).get()/.set()."""

    def __init__(self):
        self.store: dict = {}
        self._coll = None
        self._id = None

    def collection(self, name):
        self._coll = name
        return self

    def document(self, doc_id):
        self._id = doc_id
        return self

    def get(self):
        return _Snap(self.store.get((self._coll, self._id)))

    def set(self, data):
        self.store[(self._coll, self._id)] = data


@pytest.fixture
def fake_db(monkeypatch):
    db = _Docs()
    monkeypatch.setattr("google.cloud.firestore.Client", lambda **kw: db)
    return db


class TestABarcodeIsTaughtOnce:
    CODE = "8901234567897"

    def test_an_unknown_code_names_nothing(self, fake_db):
        assert cp.lookup_barcode(self.CODE) is None

    def test_a_taught_code_is_found_next_time(self, fake_db):
        assert cp.learn_barcode(self.CODE, "PARACETAMOL", CENTRE) is True
        found = cp.lookup_barcode(self.CODE)
        assert found["item_id"] == "PARACETAMOL"
        assert found["item_name"] and found["unit"]

    def test_only_a_catalogue_medicine_can_be_taught(self, fake_db):
        assert cp.learn_barcode(self.CODE, "NOT-A-MEDICINE", CENTRE) is False
        assert cp.lookup_barcode(self.CODE) is None

    def test_a_code_that_is_not_a_code_is_refused(self, fake_db):
        for bad in ("", "../x", "a/b", "12", "x" * 80):
            assert cp.learn_barcode(bad, "PARACETAMOL", CENTRE) is False
            assert cp.lookup_barcode(bad) is None

    def test_confirming_a_scanned_report_teaches_its_code(self, fake_db, monkeypatch):
        monkeypatch.setattr(cp, "write_to_ledger", lambda records: (len(records), None))
        monkeypatch.setattr(cp, "hold_overdraws", lambda result, balance_fn=None: result)
        r = cp.confirm([{"item_id": "PARACETAMOL", "local_name": "Paracetamol",
                         "event_type": "received", "quantity": 100, "unit": "tablet"}],
                       CENTRE, "barcode", barcode=self.CODE)
        assert r["barcode_learned"] is True
        assert cp.lookup_barcode(self.CODE)["item_id"] == "PARACETAMOL"
