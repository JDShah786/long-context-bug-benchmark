"""Send a prompt to a model, get the reply text back.

Each function takes `post` (the thing that talks to the internet) as a parameter,
so tests can pass a fake one.
"""
import json
import re
import time
import urllib.error
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/generate"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RETRY_STATUSES = {429, 500, 502, 503, 504}
DEFAULT_WAIT = 30  # seconds, when the server doesn't say how long


class HttpError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


class DailyLimitReached(Exception):
    """The free tier's requests-per-day cap is used up. Stop and resume tomorrow."""


def post_json(url: str, body: dict, headers: dict, timeout: float = 1800) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        raise HttpError(e.code, e.read().decode("utf-8", errors="replace")) from None


def ollama_generate(model: str, prompt: str, *, num_ctx: int, post=post_json) -> dict:
    body = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"num_ctx": num_ctx, "temperature": 0},  # without num_ctx, Ollama silently cuts long prompts
    }
    try:
        reply = post(OLLAMA_URL, body, {})
    except HttpError as e:
        if "repeat limit" in e.body:  # the model got stuck repeating itself: no answer, not a crash
            return {"text": "", "prompt_tokens": None, "error": e.body[:200]}
        raise
    return {"text": reply.get("response", ""), "prompt_tokens": reply.get("prompt_eval_count")}


def gemini_generate(model: str, prompt: str, *, key: str, post=post_json, sleep=time.sleep,
                    max_retries: int = 5) -> dict:
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    url = GEMINI_URL.format(model=model)
    for attempt in range(max_retries + 1):
        try:
            reply = post(url, body, {"x-goog-api-key": key})  # key in a header, never in the URL
            break
        except HttpError as e:
            if e.status == 429 and "PerDay" in e.body:
                raise DailyLimitReached(e.body[:300]) from None
            if e.status not in RETRY_STATUSES or attempt == max_retries:
                raise
            sleep(_retry_delay(e.body) * (attempt + 1))
    parts = (reply.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    return {"text": text, "prompt_tokens": reply.get("usageMetadata", {}).get("promptTokenCount")}


def _retry_delay(body: str) -> float:
    match = re.search(r'"retryDelay":\s*"(\d+(?:\.\d+)?)s"', body)
    return float(match.group(1)) + 1 if match else DEFAULT_WAIT
