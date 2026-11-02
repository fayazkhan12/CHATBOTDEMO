"""A natural spoken voice: POST /api/voice/speak turns a short piece of text into a WAV file the browser plays.

Why this file exists
--------------------
The voices built into a browser sound like a machine, and they read Hindi and Hinglish badly. Gemini's speech
models read the same text the way a person does (rhythm, small pauses, warmth), in Hindi, English and Hinglish.

This feature never has to work. When it says "not now" (HTTP 503: no key, no quota, a model that is gone, too busy)
the website speaks with the browser's own voice, so a quota or a wrong setting can not break a conversation.

    GET  /api/voice/status   is the natural voice on right now? (open it in a browser to check the set-up)
    POST /api/voice/speak    {"text": "...", "voice": "female|male", "lang": "hi-IN"}  ->  audio/wav

Settings (all optional, environment variables):
    TTS_ENABLED=0            switch the natural voice off
    TTS_MODEL                the speech model (default gemini-3.1-flash-tts-preview)
    TTS_FALLBACK_MODELS      comma separated models to try when the first one is not found
    TTS_VOICE_FEMALE / TTS_VOICE_MALE   Gemini voice names (default Sulafat / Achird)
    TTS_RATE_PER_MIN         requests per visitor per minute (default 90)
    TTS_HOURLY_CHARS         characters synthesised per hour for the whole site (default 150000)
    TTS_CONCURRENCY          how many sentences are synthesised at the same time (default 3)
    TTS_TIMEOUT              seconds to wait for one sentence (default 20)
    TTS_CACHE_MB             memory for finished sentences (default 40)
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import re
import sys
import time
import wave
from array import array
from collections import OrderedDict, deque
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

log = logging.getLogger("destinoway.voice")
router = APIRouter(prefix="/api/voice")

DEFAULT_MODEL = "gemini-3.1-flash-tts-preview"
DEFAULT_FALLBACK = "gemini-2.5-flash-preview-tts"
VOICES = {"female": ("TTS_VOICE_FEMALE", "Sulafat"), "male": ("TTS_VOICE_MALE", "Achird")}
MAX_CHARS = 450          # one request is one sentence or two; the website cuts longer replies into pieces

_get_client: Callable[[], Any] = lambda: None
_limit: Optional[Callable[[str, int, int], None]] = None
_ip: Callable[[Request], str] = lambda request: "unknown"


def setup(*, client: Callable[[], Any], rate_limit: Callable[[str, int, int], None], client_ip: Callable[[Request], str]) -> None:
    """server.py hands over its Gemini client, its rate limiter and its way of telling visitors apart."""
    global _get_client, _limit, _ip
    _get_client, _limit, _ip = client, rate_limit, client_ip


# ---------------------------------------------------------------- settings
def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _num(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def enabled() -> bool:
    return _env("TTS_ENABLED", "1").lower() not in ("0", "false", "off", "no")


def models() -> List[str]:
    out: List[str] = []
    for m in [_env("TTS_MODEL", DEFAULT_MODEL)] + _env("TTS_FALLBACK_MODELS", DEFAULT_FALLBACK).split(","):
        m = m.strip()
        if m and m not in out:
            out.append(m)
    return out


def voice_name(gender: str) -> str:
    env, default = VOICES.get(gender, VOICES["female"])
    name = _env(env, default)
    return name if re.fullmatch(r"[A-Za-z]{3,24}", name) else default


# ---------------------------------------------------------------- which language is this text in?
_SCRIPTS = (("hi", 0x0900, 0x097F), ("bn", 0x0980, 0x09FF), ("pa", 0x0A00, 0x0A7F), ("gu", 0x0A80, 0x0AFF), ("or", 0x0B00, 0x0B7F),
            ("ta", 0x0B80, 0x0BFF), ("te", 0x0C00, 0x0C7F), ("kn", 0x0C80, 0x0CFF), ("ml", 0x0D00, 0x0D7F))
LANG_NAMES = {"hi": "Hindi", "mr": "Marathi", "bn": "Bengali", "pa": "Punjabi", "gu": "Gujarati", "or": "Odia",
              "ta": "Tamil", "te": "Telugu", "kn": "Kannada", "ml": "Malayalam"}
# everyday Hindi words written in English letters, and not English words themselves
_HINGLISH = frozenset(
    "hai hain hoon hun tha thi kya kaise kaisa kaisi kab kahan kaun kaunsa kaunsi kitna kitne kitni aap aapka aapki aapke apna apni apne "
    "mujhe mera meri mere hum humein tum tumhara nahi nahin haan accha achha theek thik bilkul zaroor chahiye chahie karna karni karein karen "
    "kijiye dijiye batao bataiye bataye dekhiye dikhao dikhaiye raat rukna rukne jana jaana jaye jayenge ke ki ko ka se mein par aur lekin "
    "magar phir abhi kal aaj parso sasta mehnga bahut thoda zyada kam sirf wala wale wali ji bhai dost sahi wapas pehle baad liye hoga hogi "
    "honge milega milegi milenge lagega lagegi shukriya dhanyavaad namaste ruko ruk bolo boliye sunao suniye".split())


def text_language(text: str, hint: str = "") -> Tuple[str, str]:
    """('en' | 'hinglish' | 'hi' | 'mr' | 'ta' ..., a name for the style line) for the words that will be spoken."""
    counts: Dict[str, int] = {}
    latin = 0
    for ch in text:
        o = ord(ch)
        if 0x41 <= o <= 0x5A or 0x61 <= o <= 0x7A:
            latin += 1
        elif o >= 0x0900:
            for code, lo, hi in _SCRIPTS:
                if lo <= o <= hi:
                    counts[code] = counts.get(code, 0) + 1
                    break
    if counts:
        code, n = max(counts.items(), key=lambda kv: kv[1])
        if n > latin:
            if code == "hi" and str(hint).lower().startswith("mr"):
                code = "mr"
            return code, LANG_NAMES.get(code, "Hindi")
    tokens = re.findall(r"[a-z']+", text.lower())
    hits = sum(1 for t in tokens if t in _HINGLISH)
    if hits >= 2 and hits >= 0.2 * len(tokens):
        return "hinglish", "Hinglish"
    return "en", "English"


_TONE = "in a warm, friendly, relaxed voice, like a helpful person chatting on the phone, with natural rhythm and small pauses"


def directive(code: str, name: str) -> str:
    """The style line in front of the text, in the 'Say ...: text' form the speech models are built for."""
    if code == "hinglish":
        return f"Say this in natural Hinglish, pronouncing the Hindi words the way a native Hindi speaker does, {_TONE}"
    if code == "en":
        return f"Say this in a natural Indian English accent, {_TONE}"
    return f"Say this in natural, fluent {name}, {_TONE}"


_TAG = re.compile(r"<[^>]*>")
_WS = re.compile(r"\s+")


def clean_text(text: Any) -> str:
    s = _TAG.sub(" ", str(text or ""))
    s = "".join(" " if (ord(c) < 32 or ord(c) == 127) else c for c in s)
    return _WS.sub(" ", s).strip()


# ---------------------------------------------------------------- audio
def pcm_rate(mime: str) -> int:
    m = re.search(r"rate=(\d{4,6})", mime or "")
    return int(m.group(1)) if m else 24000


def trim_silence(pcm: bytes, rate: int) -> bytes:
    """Cut the silence the model leaves in front of and behind a sentence, so the answer starts and ends without dead air.
    A little is kept on both sides so no word is clipped."""
    size = len(pcm) - (len(pcm) % 2)
    if size < rate:      # under a quarter of a second: nothing worth trimming
        return pcm[:size]
    s = array("h")
    s.frombytes(pcm[:size])
    if sys.byteorder == "big":
        s.byteswap()
    win = max(1, rate // 100)    # 10 ms
    frames = (len(s) + win - 1) // win
    loud = [max(map(abs, s[i * win:(i + 1) * win])) > 300 for i in range(frames)]
    if not any(loud):
        return pcm[:size]
    first = loud.index(True)
    last = frames - 1 - loud[::-1].index(True)
    out = s[max(0, first - 5) * win:min(len(s), (last + 1 + 10) * win)]
    if sys.byteorder == "big":
        out.byteswap()
    return out.tobytes()


def to_wav(pcm: bytes, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def finish_audio(data: bytes, mime: str) -> Tuple[bytes, str]:
    """What the model sent -> (bytes the browser can play, their media type). Raw 16-bit PCM becomes a WAV file."""
    m = (mime or "").lower()
    if data[:4] == b"RIFF":
        return data, "audio/wav"
    if not m or "l16" in m or "pcm" in m:
        rate = pcm_rate(m)
        return to_wav(trim_silence(data, rate), rate), "audio/wav"
    return data, mime


# ---------------------------------------------------------------- finished sentences are kept for a while
class _Cache:
    def __init__(self) -> None:
        self.items: "OrderedDict[str, Tuple[bytes, str]]" = OrderedDict()
        self.size = 0

    def get(self, key: str) -> Optional[Tuple[bytes, str]]:
        hit = self.items.get(key)
        if hit is not None:
            self.items.move_to_end(key)
        return hit

    def put(self, key: str, value: Tuple[bytes, str]) -> None:
        limit = int(_num("TTS_CACHE_MB", 40) * 1024 * 1024)
        if len(value[0]) > limit // 4:
            return
        if key in self.items:
            self.size -= len(self.items.pop(key)[0])
        self.items[key] = value
        self.size += len(value[0])
        while self.items and (self.size > limit or len(self.items) > 600):
            _, old = self.items.popitem(last=False)
            self.size -= len(old[0])

    def clear(self) -> None:
        self.items.clear()
        self.size = 0


CACHE = _Cache()
_spent: Deque[Tuple[float, int]] = deque()                      # (time, characters) of the last hour
_breaker: Dict[str, Any] = {"until": 0.0, "fails": 0, "why": ""}
_good_model: List[str] = []                                     # the model that last worked
_inflight: Dict[str, Tuple[Any, "asyncio.Future[Tuple[bytes, str]]"]] = {}
_sems: Dict[str, Any] = {}


def reset_state() -> None:
    """For tests: forget the cache, the budget and any pause."""
    CACHE.clear()
    _spent.clear()
    _inflight.clear()
    _sems.clear()
    _good_model.clear()
    _breaker.update(until=0.0, fails=0, why="")


def blocked_for() -> float:
    return max(0.0, float(_breaker["until"]) - time.time())


def _trip(seconds: float, why: str) -> None:
    _breaker.update(until=time.time() + seconds, why=why, fails=0)
    log.warning("natural voice paused for %ds (%s); the browser voice is used meanwhile", int(seconds), why)


def budget_left() -> int:
    now = time.time()
    while _spent and now - _spent[0][0] > 3600:
        _spent.popleft()
    return int(_num("TTS_HOURLY_CHARS", 150000)) - sum(c for _, c in _spent)


def _semaphore() -> "asyncio.Semaphore":
    loop = asyncio.get_running_loop()
    key = str(id(loop))
    if key not in _sems:
        _sems.clear()
        _sems[key] = asyncio.Semaphore(max(1, int(_num("TTS_CONCURRENCY", 3))))
    return _sems[key]


class Unavailable(Exception):
    """The natural voice can not answer now; `why` is short and safe to show, `wait` says when to ask again."""

    def __init__(self, why: str, wait: float) -> None:
        super().__init__(why)
        self.why, self.wait = why, max(1.0, float(wait))


class _NoAudio(Exception):
    pass


def _kind(exc: BaseException) -> str:
    """quota | auth | model | busy | other"""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return "busy"
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    text = str(exc).lower()
    if code == 429 or "resource_exhausted" in text or "quota" in text or "rate limit" in text:
        return "quota"
    if code in (401, 403) or "api key" in text or "permission" in text and "denied" in text:
        return "auth"
    if code == 404 or ("model" in text and ("not found" in text or "not supported" in text or "is not available" in text)):
        return "model"
    if isinstance(code, int) and code >= 500:
        return "busy"
    return "other"


def _retry_hint(exc: BaseException, default: float) -> float:
    """Gemini often says 'retry in 23.5s'; use it (within reason)."""
    m = re.search(r"retry(?: in|Delay\D{0,6})\s*[\"']?(\d+(?:\.\d+)?)\s*s", str(exc), re.I)
    return min(900.0, max(10.0, float(m.group(1)) + 2)) if m else default


async def _ask(client: Any, model: str, voice: str, prompt: str) -> Tuple[bytes, str]:
    from google.genai import types as T   # imported here: the API must start even if the SDK changes

    cfg = T.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=T.SpeechConfig(voice_config=T.VoiceConfig(prebuilt_voice_config=T.PrebuiltVoiceConfig(voice_name=voice))),
    )
    resp = await asyncio.wait_for(client.aio.models.generate_content(model=model, contents=prompt, config=cfg), timeout=_num("TTS_TIMEOUT", 20))
    for cand in getattr(resp, "candidates", None) or []:
        for part in getattr(getattr(cand, "content", None), "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None)
            if data:
                return bytes(data), str(getattr(inline, "mime_type", "") or "")
    raise _NoAudio("the model answered with text, not audio")


def _failed(exc: Optional[BaseException]) -> Unavailable:
    """One more failure that is not a quota or key problem (time-out, server error, no audio). Three in a row pause the natural voice for a minute."""
    _breaker["fails"] = int(_breaker["fails"]) + 1
    log.warning("voice failed (%d in a row): %s", _breaker["fails"], str(exc)[:200])
    if _breaker["fails"] >= 3:
        _trip(60, "busy")
        return Unavailable("busy", blocked_for())
    return Unavailable("busy", 5)


async def _synthesize(prompt: str, voice: str) -> Tuple[bytes, str]:
    client = _get_client()
    order = _good_model[:1] + [m for m in models() if m not in _good_model[:1]]
    started = time.time()
    last: Optional[BaseException] = None
    missing = 0
    for model in order:
        for _ in (1, 2):            # the speech models now and then answer with text: one more try
            try:
                data, mime = await _ask(client, model, voice, prompt)
            except _NoAudio as exc:
                last = exc
                continue
            except Exception as exc:  # noqa: BLE001 - sorted below
                last = exc
                kind = _kind(exc)
                if kind == "model":
                    missing += 1
                    log.warning("speech model %s is not available: %s", model, str(exc)[:160])
                    break           # try the next model
                if kind == "quota":
                    _trip(_retry_hint(exc, 300), "quota")
                    raise Unavailable("quota", blocked_for())
                if kind == "auth":
                    _trip(900, "key")
                    raise Unavailable("key", blocked_for())
                raise _failed(exc)
            if _good_model[:1] != [model]:
                _good_model[:] = [model]
            _breaker["fails"] = 0
            out = finish_audio(data, mime)
            log.info("voice ok: model=%s voice=%s chars=%d ms=%d bytes=%d", model, voice, len(prompt), int((time.time() - started) * 1000), len(out[0]))
            return out
        else:
            raise _failed(last)     # two answers without audio
    if missing == len(order):
        _trip(900, "model")
        raise Unavailable("model", blocked_for())
    raise _failed(last)


async def _shared(key: str, make: Callable[[], Any]) -> Tuple[bytes, str]:
    """Two visitors (or a replay) asking for the same sentence at once share one synthesis; it finishes even if they leave."""
    loop = asyncio.get_running_loop()
    hit = _inflight.get(key)
    if hit and hit[0] is loop and not hit[1].done():
        return await asyncio.shield(hit[1])
    task = loop.create_task(make())

    def _done(t: "asyncio.Future[Tuple[bytes, str]]") -> None:
        if _inflight.get(key, (None, None))[1] is t:
            _inflight.pop(key, None)
        if not t.cancelled():
            t.exception()           # an error nobody is waiting for any more is not 'never retrieved'

    task.add_done_callback(_done)
    _inflight[key] = (loop, task)
    return await asyncio.shield(task)


async def _produce(key: str, prompt: str, voice: str, chars: int) -> Tuple[bytes, str]:
    sem = _semaphore()
    try:
        await asyncio.wait_for(sem.acquire(), timeout=6)
    except (asyncio.TimeoutError, TimeoutError):
        raise Unavailable("busy", 3)
    try:
        _spent.append((time.time(), chars))
        out = await _synthesize(prompt, voice)
    finally:
        sem.release()
    CACHE.put(key, out)
    return out


# ---------------------------------------------------------------- the two routes
class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: str = Field("female", max_length=10)
    lang: str = Field("", max_length=12)      # the visitor's voice language, e.g. "mr-IN": tells Marathi from Hindi


def _unavailable(why: str, wait: float) -> HTTPException:
    # the wait is in the body: a browser page can not read the Retry-After header of another site
    return HTTPException(status_code=503, detail={"error": "voice_unavailable", "why": why, "retry": int(max(1, wait))}, headers={"Retry-After": str(int(max(1, wait)))})


@router.get("/status")
async def status() -> Dict[str, Any]:
    wait = blocked_for()
    on = enabled() and _get_client() is not None
    return {
        "natural_voice": bool(on and wait <= 0),
        "enabled": enabled(), "has_key": _get_client() is not None,
        "paused_for": int(wait), "why": str(_breaker["why"]) if wait > 0 else "",
        "model": (_good_model[:1] or models()[:1] or [""])[0],
        "voices": {g: voice_name(g) for g in VOICES},
        "chars_left_this_hour": max(0, budget_left()),
    }


@router.post("/speak")
async def speak(body: SpeakIn, request: Request) -> Response:
    if not enabled() or _get_client() is None:
        raise _unavailable("off", 3600)
    wait = blocked_for()
    if wait > 0:
        raise _unavailable(str(_breaker["why"]) or "busy", wait)
    text = clean_text(body.text)
    if not any(c.isalnum() for c in text):
        raise HTTPException(status_code=400, detail="Nothing to say.")
    if len(text) > MAX_CHARS:
        raise HTTPException(status_code=400, detail=f"Send at most {MAX_CHARS} characters at a time.")
    if _limit is not None:
        _limit(f"tts:{_ip(request)}", int(_num("TTS_RATE_PER_MIN", 90)), 60)
    gender = "male" if str(body.voice).lower() == "male" else "female"
    voice = voice_name(gender)
    code, name = text_language(text, body.lang)
    prompt = f"{directive(code, name)}: {text}"
    key = hashlib.sha256(f"{models()[0]}|{voice}|{prompt}".encode("utf-8")).hexdigest()
    hit = CACHE.get(key)
    if hit is None:
        if budget_left() < len(text):
            raise _unavailable("budget", 600)
        try:
            hit = await _shared(key, lambda: _produce(key, prompt, voice, len(text)))
        except Unavailable as exc:
            raise _unavailable(exc.why, exc.wait)
        served = "miss"
    else:
        served = "hit"
    return Response(content=hit[0], media_type=hit[1], headers={"X-Voice-Cache": served, "Cache-Control": "no-store"})
