"""Tests for the model clients (src/models.py). No network: a fake `post` stands in for the internet.

Requirements these encode:
- Ollama: always sends num_ctx (so long prompts are never silently cut), temperature 0, no streaming, JSON mode.
- Gemini: pinned model in the URL, key in a header (never the URL), temperature 0, JSON mode;
  returns only the answer text, skipping "thought" parts; empty reply if nothing came back.
- Gemini rate limits: per-minute 429 / server errors wait and retry; a per-day limit stops with DailyLimitReached;
  give up after max retries.
- Both return {"text": str, "prompt_tokens": int | None}.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from models import DailyLimitReached, HttpError, gemini_generate, ollama_generate  # noqa: E402


class FakePost:
    """Records each request and returns (or raises) the next scripted reply."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, url, body, headers):
        self.calls.append({"url": url, "body": body, "headers": headers})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


# ---------- Ollama ----------

OLLAMA_OK = {"response": '{"buggy_line": "a", "fixed_line": "b"}', "prompt_eval_count": 31000}


def test_ollama_sends_num_ctx_temperature_and_json_mode():
    post = FakePost(OLLAMA_OK)
    ollama_generate("qwen2.5-coder:7b", "PROMPT", num_ctx=40960, post=post)
    body = post.calls[0]["body"]
    assert body["model"] == "qwen2.5-coder:7b"
    assert body["prompt"] == "PROMPT"
    assert body["stream"] is False
    assert body["format"] == "json"
    assert body["options"]["num_ctx"] == 40960
    assert body["options"]["temperature"] == 0


def test_ollama_returns_text_and_prompt_tokens():
    out = ollama_generate("m", "P", num_ctx=40960, post=FakePost(OLLAMA_OK))
    assert out == {"text": OLLAMA_OK["response"], "prompt_tokens": 31000}


def test_ollama_num_ctx_is_required():
    with pytest.raises(TypeError):
        ollama_generate("m", "P", post=FakePost(OLLAMA_OK))  # forgetting it must be impossible


# ---------- Gemini ----------

def gemini_reply(*parts, prompt_tokens=30000):
    return {
        "candidates": [{"content": {"parts": list(parts)}}],
        "usageMetadata": {"promptTokenCount": prompt_tokens},
    }


ANSWER = '{"buggy_line": "a", "fixed_line": "b"}'


def call_gemini(post, sleep=lambda s: None, **kw):
    return gemini_generate("gemini-x-flash", "PROMPT", key="SECRET", post=post, sleep=sleep, **kw)


def test_gemini_request_shape():
    post = FakePost(gemini_reply({"text": ANSWER}))
    call_gemini(post)
    call = post.calls[0]
    assert "models/gemini-x-flash:generateContent" in call["url"]
    assert "SECRET" not in call["url"]
    assert call["headers"]["x-goog-api-key"] == "SECRET"
    assert call["body"]["contents"][0]["parts"][0]["text"] == "PROMPT"
    assert call["body"]["generationConfig"]["temperature"] == 0
    assert call["body"]["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_returns_text_and_prompt_tokens():
    assert call_gemini(FakePost(gemini_reply({"text": ANSWER}))) == {"text": ANSWER, "prompt_tokens": 30000}


def test_gemini_skips_thought_parts():
    reply = gemini_reply({"text": "let me think...", "thought": True}, {"text": ANSWER})
    assert call_gemini(FakePost(reply))["text"] == ANSWER


def test_gemini_no_candidates_gives_empty_text():
    out = call_gemini(FakePost({"usageMetadata": {"promptTokenCount": 5}}))
    assert out == {"text": "", "prompt_tokens": 5}


def test_gemini_per_minute_limit_waits_and_retries():
    slept = []
    post = FakePost(HttpError(429, '{"error": {"status": "RESOURCE_EXHAUSTED", "message": "per minute"}}'),
                    gemini_reply({"text": ANSWER}))
    out = call_gemini(post, sleep=slept.append)
    assert out["text"] == ANSWER
    assert len(post.calls) == 2
    assert slept and slept[0] > 0


def test_gemini_uses_server_suggested_retry_delay():
    slept = []
    body = '{"error": {"details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "23s"}]}}'
    call_gemini(FakePost(HttpError(429, body), gemini_reply({"text": ANSWER})), sleep=slept.append)
    assert slept[0] >= 23


def test_gemini_server_error_retries():
    post = FakePost(HttpError(503, "overloaded"), gemini_reply({"text": ANSWER}))
    assert call_gemini(post)["text"] == ANSWER


def test_gemini_daily_limit_stops():
    body = '{"error": {"details": [{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}'
    with pytest.raises(DailyLimitReached):
        call_gemini(FakePost(HttpError(429, body)))


def test_gemini_gives_up_after_max_retries():
    post = FakePost(*[HttpError(503, "down")] * 3)
    with pytest.raises(HttpError):
        call_gemini(post, max_retries=2)
    assert len(post.calls) == 3


def test_gemini_bad_request_is_not_retried():
    post = FakePost(HttpError(400, "bad model name"))
    with pytest.raises(HttpError):
        call_gemini(post)
    assert len(post.calls) == 1


def test_ollama_repeat_loop_counts_as_no_answer():
    post = FakePost(HttpError(500, '{"error":"prediction aborted, token repeat limit reached"}'))
    out = ollama_generate("m", "P", num_ctx=40960, post=post)
    assert out["text"] == ""
    assert "repeat" in out["error"]


def test_ollama_other_errors_still_raise():
    with pytest.raises(HttpError):
        ollama_generate("m", "P", num_ctx=40960, post=FakePost(HttpError(500, "model not found")))
