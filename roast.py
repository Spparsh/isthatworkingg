#!/usr/bin/env python3
"""
ROAST-MY-CODE 🔥
Your code walks in. It does not walk out the same.

Works with ANY OpenAI-compatible API (OpenAI, Groq, Sarvam, Ollama, whatever).
Pure Python standard library - nothing to pip install.

Setup:
    export ROAST_API_KEY="sk-..."
    export ROAST_BASE_URL="https://api.openai.com/v1"   # or your provider
    export ROAST_MODEL="gpt-4o-mini"                    # or any chat model

Usage:
    python roast.py my_broken_script.py        # roast a file
    cat main.py | python roast.py              # roast from stdin
    python roast.py                            # interactive paste mode
    python roast.py terrible.py --level 5      # mercy is off the table
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BURNS = {
    1: "gentle mentor. Disappointed-parent energy. Barely a roast.",
    2: "playful teasing between friends. A light singe.",
    3: "standard-issue savage senior dev. Funny but fair.",
    4: "open-mic night. No mercy, still no slurs, just pain.",
    5: "nuclear. Roast this code like it insulted your family. Maximum creativity, zero holding back.",
}

SYSTEM_PROMPT = """You are ROAST-MY-CODE, a savage but secretly loving senior developer.
The user will paste code. You MUST:
1. Roast the code with 3 witty, specific burns. Reference the actual code you see —
   no generic advice. Be funny. Be cutting. Never be boring.
2. End every roast with the line: "VERDICT: {verdict}" where the verdict is one of
   /10 (e.g. "VERDICT: 3/10"), rating how much pain this code caused you.
3. Then show a fixed version of the single worst offender, as a short code block.
Keep the whole thing under 200 words. You are performing comedy, not a code review."""


def check_api_key() -> None:
    if not os.environ.get("ROAST_API_KEY"):
        sys.exit(
            "🔥 No API key set. Even cruelty needs credentials.\n"
            "   export ROAST_API_KEY=\"sk-...\"\n"
            "   (optionally ROAST_BASE_URL and ROAST_MODEL for other providers)\n"
        )


def fetch_roast(code: str, level: int) -> str:
    api_key = os.environ["ROAST_API_KEY"]
    base_url = os.environ.get("ROAST_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("ROAST_MODEL", "gpt-4o-mini")

    intensity = BURNS[level]
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Intensity level {level}/5 — you are a {intensity}\n\n```\n{code}\n```",
                    },
                ],
                "temperature": 1.0,
            }
        ).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        sys.exit(f"\n🔥 The API rejected us. Even the machine is judging you. ({e.code} {e.read().decode('utf-8', 'replace')[:200]})")
    except urllib.error.URLError as e:
        sys.exit(f"\n🔥 Cannot reach the API: {e}")


def get_code_from_user() -> str:
    print("Paste your code. Press Ctrl-D (Ctrl-Z on Windows) when the shame is complete:")
    return sys.stdin.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Your code walks in. It does not walk out the same.")
    parser.add_argument("file", nargs="?", help="file to roast (reads stdin if omitted)")
    parser.add_argument("--level", type=int, choices=range(1, 6), default=3, help="roast intensity 1-5 (default 3)")
    args = parser.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8") as f:
            code = f.read()
    elif not sys.stdin.isatty():
        code = sys.stdin.read()
    else:
        code = get_code_from_user()

    if not code.strip():
        sys.exit("🔥 You pasted nothing. Bold of you to show up with empty hands.")

    check_api_key()

    print(f"\n🔥 ROASTING AT INTENSITY {args.level}/5 🔥\n" + "-" * 50)
    print(fetch_roast(code, args.level))
    print("-" * 50 + "\nRemember: we roast because we love. Mostly.\n")


if __name__ == "__main__":
    main()
