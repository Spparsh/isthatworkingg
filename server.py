#!/usr/bin/env python3
"""
ROAST-MY-CODE server 🔥
Serves the web UI and proxies calls to the Sarvam AI API,
so your API key never touches the browser.

Setup:
    export SARVAM_API_KEY="your-key-here"     # from dashboard.sarvam.ai
    python server.py
    open http://localhost:8666

Needs nothing but Python 3 (no pip installs - pure standard library).
"""

import base64
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

import urllib.error
import urllib.request

PORT = 8666
HERE = os.path.dirname(os.path.abspath(__file__))


def resolve_api_key():
    """Find the key: env var -> sarvam_key.txt next to this file -> ask at startup."""
    key = os.environ.get("SARVAM_API_KEY", "").strip()
    if key:
        return key, "environment variable"
    key_file = os.path.join(HERE, "sarvam_key.txt")
    if os.path.isfile(key_file):
        with open(key_file, encoding="utf-8") as f:
            k = f.read().strip()
            if k:
                return k, key_file
    print("\nNo API key found. Get one free at dashboard.sarvam.ai")
    try:
        k = input("Paste your Sarvam API key (it stays on this machine): ").strip()
        with open(key_file, "w", encoding="utf-8") as f:
            f.write(k)
        print(f"Saved to {os.path.basename(key_file)} so you won't be asked again.")
        return k, "interactive"
    except Exception:
        return "", "none"


API_KEY, KEY_SOURCE = resolve_api_key()
API_BASE = os.environ.get("SARVAM_BASE_URL", "https://api.sarvam.ai").rstrip("/")
CHAT_MODEL = os.environ.get("ROAST_MODEL", "sarvam-105b-conversations")  # fast, no reasoning phase; set "sarvam-105b" for slower/deeper burns


class SarvamError(Exception):
    """Non-200 reply from the Sarvam API."""

    def __init__(self, status, body):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body = body


def api_post(url, payload, timeout=120):
    """POST JSON to Sarvam using only the standard library. Returns (status, content_type, body)."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"api-subscription-key": API_KEY, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read()


def api_post_stream(url, payload, timeout=240):
    """POST JSON and return the live response object for line-by-line SSE streaming."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"api-subscription-key": API_KEY, "Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    if resp.status != 200:
        body = resp.read().decode("utf-8", errors="replace")
        resp.close()
        raise SarvamError(resp.status, body)
    return resp


INTENSITY = {
    1: "a gentle mentor. Disappointed-parent energy. Barely a roast.",
    2: "playful teasing between friends. A light singe.",
    3: "a standard-issue savage senior dev. Funny but fair.",
    4: "an open-mic comedian. No mercy, just pain. Still no slurs, ever.",
    5: "NUCLEAR. Roast this code like it insulted your family. Maximum creativity, zero holding back.",
}

SYSTEM_PROMPT = """You are ROAST-MY-CODE, a savage but secretly loving senior developer.
The user will paste code. Respond in EXACTLY this format, in this order:

SPOKEN:
<the roast written as 3 to 5 short punchy sentences meant to be READ ALOUD by a voice assistant, one after another. No code blocks, no markdown symbols, no asterisks or backticks. Plain flowing speech only. It must land as comedy when heard, not read.>

ROAST:
<3 witty, specific burns that reference the actual code you see. No generic advice. Be funny. Be cutting. Never boring. Never cruel about the person - only the code.>

VERDICT: <number>/10
(<rate how much pain this code caused you, 0 = art, 10 = call the authorities>)

If the language requested is Hindi, write the ENTIRE response in Hindi (Devanagari script) -
but ALWAYS keep the section labels SPOKEN:, ROAST: and VERDICT: exactly as written, in English.
Never translate the labels into Hindi.
Keep the roast under 180 words."""

SPEAKERS = [
    "shubh", "aditya", "ritu", "priya", "neha", "rahul",
    "amit", "dev", "ishita", "shreya", "rohan", "kavya", "simran", "tanya",
]

SENTENCE_END = ('.', '!', '?', '\u0964', '\u0965', '\n')  # includes Devanagari danda

# section markers; the Hindi variants exist because some models translate the labels
SPOKEN_MARKERS = ("SPOKEN:", "\u0938\u094d\u092a\u094b\u0915\u0928:")
ROAST_MARKERS = ("ROAST:", "\u0930\u094b\u0938\u094d\u091f:")
VERDICT_RE = r"(?:VERDICT|\u0935\u094d\u0939\u0930\u094d\u0926\u0940\u0915\u094d\u091f)\s*:\s*([\d.]+)\s*/\s*10"


def find_marker(s, markers):
    """Return the first marker found in s: (marker, index), else (None, -1)."""
    best = (None, -1)
    for m in markers:
        i = s.find(m)
        if i != -1 and (best[1] == -1 or i < best[1]):
            best = (m, i)
    return best


def partial_marker_tail(s: str, markers=ROAST_MARKERS) -> str:
    """If s ends with a partial prefix of any marker (e.g. 'ROAS'), return that tail."""
    for marker in markers:
        for k in range(min(len(s), len(marker) - 1), 0, -1):
            if marker.startswith(s[-k:]):
                return s[-k:]
    return ""


def take_sentences(buf: str):
    """Split complete sentences off the front of buf. Returns (sentences, remainder)."""
    out = []
    while True:
        idx = -1
        for i, ch in enumerate(buf):
            if ch in SENTENCE_END:
                idx = i
                break
        if idx == -1:
            break
        sent = buf[: idx + 1].strip()
        buf = buf[idx + 1 :]
        if sent:
            out.append(sent)
    return out, buf


def tts_b64(text: str, speaker: str, language: str, pace: float):
    """Synthesize one chunk of speech; returns base64 WAV or None on failure."""
    if len(text) > 2400:
        cut = text[:2400]
        text = cut[: cut.rfind(". ") + 1] or cut
    try:
        status, ctype, body = api_post(
            f"{API_BASE}/text-to-speech",
            {
                "text": text,
                "target_language_code": language,
                "speaker": speaker,
                "model": "bulbul:v3",
                "pace": pace,
                "speech_sample_rate": 24000,
                "output_audio_codec": "wav",
            },
            timeout=90,
        )
    except (urllib.error.URLError, OSError):
        return None
    if status != 200:
        return None
    if "application/json" in ctype:
        try:
            return (json.loads(body).get("audios") or [None])[0]
        except ValueError:
            return None
    return base64.b64encode(body).decode()


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, ctype="application/json"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def _need_key(self):
        if not API_KEY:
            self._send(500, {"error": "No SARVAM_API_KEY set on the server. Even cruelty needs credentials. Run: export SARVAM_API_KEY=..."})
            return True
        return False

    # ---------------- routes ----------------

    def do_GET(self):
        if self.path == "/":
            try:
                with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "roast.html"), "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(404, "roast.html not found next to server.py", "text/plain")
        elif self.path == "/api/config":
            self._send(200, {"has_key": bool(API_KEY), "model": CHAT_MODEL, "speakers": SPEAKERS})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            if self.path == "/api/roast":
                self.handle_roast()
            elif self.path == "/api/roast-voice":
                self.handle_roast_voice()
            elif self.path == "/api/speak":
                self.handle_speak()
            else:
                self._send(404, {"error": "not found"})
        except urllib.error.URLError as e:
            self._send(502, {"error": f"Sarvam API unreachable: {e}"})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": str(e)})

    # ---------------- /api/roast ----------------

    def handle_roast(self):
        if self._need_key():
            return
        body = self._json_body()
        code = (body.get("code") or "").strip()
        level = int(body.get("level", 3))
        language = body.get("language", "en-IN")

        if not code:
            self._send(400, {"error": "You pasted nothing. Bold of you to show up with empty hands."})
            return
        if len(code) > 100_000:
            self._send(400, {"error": "That is not code, that is a memoir. Trim it down."})
            return

        lang_note = "Respond in Hindi (Devanagari script)." if language == "hi-IN" else "Respond in English."
        user_msg = (
            f"Intensity level {level}/5 - you are {INTENSITY.get(level, INTENSITY[3])}\n"
            f"Language: {lang_note}\n\n"
            f"```\n{code}\n```"
        )

        status, _, body = api_post(
            f"{API_BASE}/v1/chat/completions",
            {
                "model": CHAT_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 1.0,
                "max_tokens": 8000,
            },
            timeout=120,
        )
        if status != 200:
            self._send(status, {"error": f"The model refused to witness this. ({body.decode('utf-8', 'replace')[:300]})"})
            return

        text = json.loads(body)["choices"][0]["message"]["content"]
        self._send(200, parse_roast(text, language))

    # ---------------- /api/roast-voice (streaming: LLM -> sentences -> TTS as they arrive) ----------------

    def handle_roast_voice(self):
        if self._need_key():
            return
        body = self._json_body()
        code = (body.get("code") or "").strip()
        level = int(body.get("level", 3))
        language = body.get("language", "en-IN")
        speaker = body.get("speaker", "shubh")
        pace = float(body.get("pace", 1.0))

        if not code:
            self._send(400, {"error": "You pasted nothing. Bold of you to show up with empty hands."})
            return
        if len(code) > 100_000:
            self._send(400, {"error": "That is not code, that is a memoir. Trim it down."})
            return

        lang_note = "Respond in Hindi (Devanagari script)." if language == "hi-IN" else "Respond in English."
        user_msg = (
            f"Intensity level {level}/5 - you are {INTENSITY.get(level, INTENSITY[3])}\n"
            f"Language: {lang_note}\n\n"
            f"```\n{code}\n```"
        )

        # switch to a raw streaming response (ndjson, one event per line)
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        def emit(obj):
            try:
                self.wfile.write((json.dumps(obj) + "\n").encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                raise  # browser gave up; stop the pipeline

        spoken_buf = ""      # text waiting for a sentence boundary
        spoken_done = False
        in_spoken = False
        pending = ""          # sentences batched until ~120 chars, to limit TTS calls
        full = ""             # everything the model has said (for the verdict)
        display_hold = ""     # display text held back in case it is a partial ROAST: marker

        def speak_pending(force=False):
            nonlocal pending
            if pending.strip() and force:
                audio = tts_b64(pending.strip(), speaker, language, pace)
                if audio:
                    emit({"type": "audio", "b64": audio})
                pending = ""

        try:
            try:
                resp = api_post_stream(
                    f"{API_BASE}/v1/chat/completions",
                    {
                        "model": CHAT_MODEL,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_msg},
                        ],
                        "temperature": 1.0,
                        "stream": True,
                        "max_tokens": 8000,  # sarvam-105b reasons first; the default cap can starve the answer
                    },
                    timeout=240,
                )
            except SarvamError as e:
                emit({"type": "error", "message": f"The model refused to witness this. ({str(e.body)[:200]})"})
                return
            except (urllib.error.URLError, OSError) as e:
                emit({"type": "error", "message": f"Sarvam API unreachable: {e}"})
                return

            for raw_line in resp:
                raw = raw_line.decode("utf-8", errors="replace").strip()
                if not raw or not raw.startswith("data:"):
                    continue
                data = raw[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except ValueError:
                    continue
                # sarvam-105b is a reasoning model: ignore reasoning_content, keep content only
                delta = (chunk.get("choices") or [{}])[0].get("delta", {}).get("content") or ""
                if not delta:
                    continue
                full += delta

                full_marker_check = spoken_buf + delta

                if spoken_done:
                    # streaming the written roast + verdict after the voice part
                    emit({"type": "roast", "data": delta})
                    continue

                if not in_spoken:
                    m, _ = find_marker(full_marker_check, SPOKEN_MARKERS)
                    if m is None:
                        spoken_buf = full_marker_check  # keep accumulating: the marker may arrive split across chunks
                        continue
                    in_spoken = True
                    _, delta = full_marker_check.split(m, 1)
                    delta = delta.lstrip()
                    full_marker_check = delta
                elif find_marker(full_marker_check, ROAST_MARKERS)[0] is not None:
                    # voice part is finished; flush what's left, then switch to written text
                    tail = partial_marker_tail(display_hold)
                    flush = display_hold[: len(display_hold) - len(tail)].rstrip()
                    if flush:
                        emit({"type": "text", "data": flush + "\n"})
                    display_hold = ""
                    rm, _ = find_marker(full_marker_check, ROAST_MARKERS)
                    before, after = full_marker_check.split(rm, 1)
                    if before.strip():
                        pending += " " + before.strip()
                    speak_pending(force=True)
                    spoken_done = True
                    if after.strip():
                        emit({"type": "roast", "data": after})
                    continue

                spoken_buf = full_marker_check
                # live display of what is being spoken, holding back any partial ROAST: marker
                display_hold += delta
                hold = partial_marker_tail(display_hold)
                if hold:
                    safe, display_hold = display_hold[: len(display_hold) - len(hold)], hold
                else:
                    safe, display_hold = display_hold, ""
                if safe:
                    emit({"type": "text", "data": safe})
                sentences, spoken_buf = take_sentences(spoken_buf)
                for s in sentences:
                    pending += " " + s
                    if len(pending) > 120:
                        speak_pending(force=True)

            resp.close()

            # stream ended - flush leftovers
            if not spoken_done and spoken_buf.strip():
                sentences, _ = take_sentences(spoken_buf + ".")
                for s in sentences:
                    pending += " " + s
            speak_pending(force=True)

            vm = re.search(VERDICT_RE, full)
            if vm:
                emit({"type": "verdict", "value": f"{vm.group(1)}/10"})
            emit({"type": "done"})
        except (BrokenPipeError, ConnectionResetError):
            return  # browser closed the tab; stop quietly
        except (urllib.error.URLError, OSError) as e:
            try:
                emit({"type": "error", "message": f"Sarvam API unreachable: {e}"})
            except Exception:
                pass

    # ---------------- /api/speak ----------------

    def handle_speak(self):
        if self._need_key():
            return
        body = self._json_body()
        text = (body.get("text") or "").strip()
        if not text:
            self._send(400, {"error": "Nothing to say. The roast left it speechless."})
            return

        # TTS limits: 2500 chars on bulbul:v3. Trim on a sentence boundary.
        if len(text) > 2400:
            cut = text[:2400]
            text = cut[: cut.rfind(". ") + 1] or cut

        payload = {
            "text": text,
            "target_language_code": body.get("language", "en-IN"),
            "speaker": body.get("speaker", "shubh"),
            "model": "bulbul:v3",
            "pace": float(body.get("pace", 1.0)),
            "speech_sample_rate": 24000,
            "output_audio_codec": "wav",
        }

        try:
            status, ctype, body = api_post(f"{API_BASE}/text-to-speech", payload, timeout=120)
        except (urllib.error.URLError, OSError) as e:
            self._send(502, {"error": f"The voice is unreachable: {e}"})
            return
        if status != 200:
            self._send(status, {"error": f"The voice choked on your code. ({body.decode('utf-8', 'replace')[:300]})"})
            return

        if "application/json" in ctype:
            data = json.loads(body)
            audio_b64 = (data.get("audios") or [None])[0]
            if not audio_b64:
                self._send(502, {"error": "Sarvam returned no audio."})
                return
            self._send(200, base64.b64decode(audio_b64), "audio/wav")
        else:
            # Some deployments stream raw audio bytes.
            self._send(200, body, ctype if ctype.startswith("audio/") else "audio/wav")

    def log_message(self, *args):  # quieter console
        pass


def parse_roast(text: str, language: str) -> dict:
    """Pull ROAST / VERDICT / SPOKEN out of the model output, with forgiving fallbacks."""

    def grab(pattern, default):
        m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else default

    sm, _ = find_marker(text, SPOKEN_MARKERS)
    roast = grab(r"(?:ROAST:|\u0930\u094b\u0938\u094d\u091f:)\s*\n?(.*?)(?:\n\s*(?:VERDICT|\u0935\u094d\u0939\u0930\u094d\u0926\u0940\u0915\u094d\u091f):|$)", text.strip())
    spoken = grab(r"(?:SPOKEN:|\u0938\u094d\u092a\u094b\u0915\u0928:)\s*\n?(.*)$", roast if sm is None else text)

    vm = re.search(VERDICT_RE, text, re.IGNORECASE)
    verdict = f"{vm.group(1)}/10" if vm else "?/10"

    if sm is not None:
        spoken = text.rsplit(sm, 1)[1].strip()
    # if no dedicated spoken section, synthesize a speakable version
    if not spoken or spoken == roast:
        spoken = re.sub(r"```[\s\S]*?```", " ", roast)
        spoken = re.sub(r"[*_`#>|]", "", spoken)
        sentences = re.split(r"(?<=[.!?])\s+", spoken)
        spoken = " ".join(sentences[:4])[:2000]

    return {"roast": roast, "verdict": verdict, "spoken": spoken, "language": language}


if __name__ == "__main__":
    if not API_KEY:
        print("!! No API key available. The page will load but roasting will fail.")
    else:
        print(f"* API key found via {KEY_SOURCE}")
    print(f"* Roast server burning at http://localhost:{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
