"""Spoken read-back through Cloud Text-to-Speech.

The Report page reads every report back before it is saved. It used the
phone's own speech engine, and most phones have no Telugu, Marathi or Bengali
voice: the engine skipped the words it could not pronounce and read out only
the digits. Cloud Text-to-Speech has Indian voices for all five languages.

The browser engine stays as the fallback if this call fails, so the read-back
degrades rather than disappears.
"""

from __future__ import annotations

import base64
import hashlib
import os
import threading
from collections import OrderedDict

PROJECT = os.getenv("GCP_PROJECT", os.getenv("GOOGLE_CLOUD_PROJECT", "daysupply"))
VOICES = {"en": "en-IN", "hi": "hi-IN", "mr": "mr-IN", "te": "te-IN", "bn": "bn-IN"}
MAX_CHARS = 600
_CACHE: "OrderedDict[str, bytes]" = OrderedDict()
_CACHE_SIZE = 300
_lock = threading.Lock()
_session = None


def _get_session():
    global _session
    if _session is None:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
        _session = AuthorizedSession(creds)
    return _session


def synthesize(text: str, lang: str) -> bytes:
    """MP3 audio of `text` in the voice for `lang`. Cached in process."""
    text = (text or "").strip()[:MAX_CHARS]
    if not text:
        raise ValueError("nothing to say")
    code = VOICES.get(lang, "en-IN")
    key = hashlib.sha1(f"{code}|{text}".encode("utf-8")).hexdigest()
    with _lock:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
    r = _get_session().post(
        "https://texttospeech.googleapis.com/v1/text:synthesize",
        headers={"x-goog-user-project": PROJECT},
        json={"input": {"text": text}, "voice": {"languageCode": code},
              "audioConfig": {"audioEncoding": "MP3", "speakingRate": 0.92}},
        timeout=15)
    r.raise_for_status()
    audio = base64.b64decode(r.json()["audioContent"])
    with _lock:
        _CACHE[key] = audio
        if len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
    return audio
