# ISTHATWORKINGG?

> **Your code walks in. It does not walk out the same.**  
> Now with a live voice.

**ISTHATWORKINGG?** is an AI-powered code roaster that takes your code, judges it, destroys it verbally, and reads the roast out loud.

Powered by **Sarvam AI** for AI-generated roasts and **Bulbul v3 Text-to-Speech** for voice output.

---

## What's Inside

```text
ISTHATWORKINGG/
│
├── server.py
│   └── Tiny local server that:
│       • Serves the web UI
│       • Talks to Sarvam AI
│       • Generates the roast
│       • Uses Bulbul v3 for text-to-speech
│
├── roast.html
│   └── Main web interface
│       IMPORTANT: Run through server.py.
│       Do NOT open this file directly.
│
└── roast.py
    └── Original command-line code roaster
        No UI. No voice. Just violence.
```

## Run It

Make sure Python is installed.

Start the server:

```bash
python server.py
```

Then open:

```text
http://localhost:8666
```

## How to Use

1. Paste your questionable code into the editor.
2. Choose your **Roast Intensity**:
   - `1` — Toasted
   - `2` — Crispy
   - `3` — Roasted
   - `4` — Charred
   - `5` — Nuclear
3. Choose your language:
   - English
   - Hindi
4. Pick a voice.
5. Set the rant speed.
6. Hit **ROAST ME**.
7. Reconsider your career choices.

## Features

- AI-powered code roasting
- Live voice roasts
- 5 roast intensity levels
- English & Hindi support
- Multiple voice options
- Adjustable rant speed
- Sarvam AI integration
- Bulbul v3 Text-to-Speech
- Browser-based interface
- Bonus CLI roaster

## Important

Don't open `roast.html` directly.

The interface is served through `server.py` because the backend handles communication with the AI and text-to-speech APIs.

```bash
python server.py
```

Then visit `http://localhost:8666`.

---

### We roast because we love.

**Mostly.**
