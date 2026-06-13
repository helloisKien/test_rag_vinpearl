"""llm.py — Lớp LLM ĐA-PROVIDER cho ABSA (Sprint 2, Bước 5.0).

Owner: Trương Anh Long (KE, DA10). Một interface chung `complete_json()`; team chọn provider/
model/key qua .env — KHÔNG sửa code ABSA khi đổi provider (giống "model-tham-số" ở Bước 2).

Provider hỗ trợ (gọi qua HTTP `requests`, KHÔNG cần cài SDK riêng):
  - openai   : api.openai.com (chat completions, JSON mode)
  - gemini   : generativelanguage.googleapis.com
  - ollama   : localhost:11434 (offline, miễn phí)
  - claude   : api.anthropic.com (messages)
Tất cả nhận system+user, trả về DICT (parse JSON). Có cache theo (provider,model,hash(prompt))
để chạy lại không gọi lại API (tiết kiệm tiền + nhanh).

Cấu hình (.env — KHÔNG commit):
  LLM_PROVIDER=openai|gemini|ollama|claude
  LLM_MODEL=gpt-4o-mini | gemini-1.5-flash | qwen2.5 | claude-haiku-4-5-20251001
  OPENAI_API_KEY=...  / GOOGLE_API_KEY=... / ANTHROPIC_API_KEY=...
  OLLAMA_HOST=http://localhost:11434   (tùy chọn)

Dùng:
  from knowledge_engineering.enrichment.llm import complete_json
  out = complete_json(system="...", user="...", temperature=0)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

CACHE_DIR = Path("knowledge_engineering/enrichment/.llm_cache")
TIMEOUT = 60          # cloud API (nhanh)
TIMEOUT_OLLAMA = 300  # local CPU chậm hơn nhiều -> timeout dài hơn
MAX_RETRY = 3
MAX_TOKENS = 800      # cap output (JSON ABSA ngắn) — chặn model "lảm nhảm" tốn token


class FatalLLMError(RuntimeError):
    """Lỗi KHÔNG nên retry (sai key/hết quota/request sai) — dừng ngay, đừng đốt thêm."""


# ---------------------------------------------------------------------------
# Config từ env
# ---------------------------------------------------------------------------
def _cfg() -> dict:
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    return {
        "provider": provider,
        "model": os.getenv("LLM_MODEL", _default_model(provider)),
        "openai_key": os.getenv("OPENAI_API_KEY"),
        "google_key": os.getenv("GOOGLE_API_KEY"),
        "anthropic_key": os.getenv("ANTHROPIC_API_KEY"),
        "ollama_host": os.getenv("OLLAMA_HOST", "http://localhost:11434"),
    }


def _default_model(provider: str) -> str:
    return {
        "openai": "gpt-4o-mini",
        "gemini": "gemini-1.5-flash",
        "ollama": "qwen2.5",
        "claude": "claude-haiku-4-5-20251001",
    }.get(provider, "gpt-4o-mini")


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
def _cache_key(provider: str, model: str, system: str, user: str) -> str:
    h = hashlib.sha256(f"{provider}|{model}|{system}|{user}".encode()).hexdigest()[:32]
    return h


def _cache_get(key: str) -> dict | None:
    f = CACHE_DIR / f"{key}.json"
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _cache_put(key: str, value: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(
        json.dumps(value, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Parse JSON từ text trả về (model đôi khi bọc ```json ... ```)
# ---------------------------------------------------------------------------
def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip().rstrip("`").strip()
    # cắt từ { đầu tới } cuối nếu có rác quanh
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b > a:
        text = text[a:b + 1]
    return json.loads(text)


# ---------------------------------------------------------------------------
# Adapter từng provider (HTTP)
# ---------------------------------------------------------------------------
def _raise_for_status_classified(r) -> None:
    """4xx auth/quota/bad-request -> FatalLLMError (KHÔNG retry). Còn lại -> raise thường (retry)."""
    if r.status_code in (400, 401, 403, 404):
        raise FatalLLMError(f"HTTP {r.status_code} (sai key/request/model — KHÔNG retry): "
                            f"{r.text[:200]}")
    if r.status_code == 429:
        raise FatalLLMError(f"HTTP 429 (hết quota/rate-limit — DỪNG để khỏi đốt thêm): "
                            f"{r.text[:200]}")
    r.raise_for_status()  # 5xx/khác -> retry


def _call_openai(cfg, system, user, temperature) -> str:
    if not cfg["openai_key"]:
        raise FatalLLMError("Thiếu OPENAI_API_KEY trong .env")
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {cfg['openai_key']}"},
        json={
            "model": cfg["model"],
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": MAX_TOKENS,                     # cap chống lảm nhảm
            "response_format": {"type": "json_object"},
        },
        timeout=TIMEOUT,
    )
    _raise_for_status_classified(r)
    return r.json()["choices"][0]["message"]["content"]


def _call_gemini(cfg, system, user, temperature) -> str:
    if not cfg["google_key"]:
        raise FatalLLMError("Thiếu GOOGLE_API_KEY trong .env")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{cfg['model']}:generateContent?key={cfg['google_key']}")
    r = requests.post(
        url,
        json={
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"parts": [{"text": user}]}],
            "generationConfig": {"temperature": temperature,
                                 "maxOutputTokens": MAX_TOKENS,
                                 "responseMimeType": "application/json"},
        },
        timeout=TIMEOUT,
    )
    _raise_for_status_classified(r)
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _call_ollama(cfg, system, user, temperature) -> str:
    r = requests.post(
        f"{cfg['ollama_host']}/api/chat",
        json={
            "model": cfg["model"],
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature},
        },
        timeout=TIMEOUT_OLLAMA,  # local CPU chậm
    )
    r.raise_for_status()
    return r.json()["message"]["content"]


def _call_claude(cfg, system, user, temperature) -> str:
    if not cfg["anthropic_key"]:
        raise FatalLLMError("Thiếu ANTHROPIC_API_KEY trong .env")
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": cfg["anthropic_key"],
                 "anthropic-version": "2023-06-01"},
        json={
            "model": cfg["model"],
            "max_tokens": MAX_TOKENS,
            "temperature": temperature,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=TIMEOUT,
    )
    _raise_for_status_classified(r)
    return r.json()["content"][0]["text"]


_ADAPTERS = {
    "openai": _call_openai,
    "gemini": _call_gemini,
    "ollama": _call_ollama,
    "claude": _call_claude,
}


# ---------------------------------------------------------------------------
# Interface công khai
# ---------------------------------------------------------------------------
def complete_json(system: str, user: str, temperature: float = 0.0,
                  use_cache: bool = True) -> dict:
    """Gọi LLM (provider theo .env), trả về DICT. Có cache + retry. Raise nếu parse fail."""
    cfg = _cfg()
    adapter = _ADAPTERS.get(cfg["provider"])
    if adapter is None:
        raise ValueError(f"LLM_PROVIDER không hỗ trợ: {cfg['provider']} "
                         f"(chọn: {list(_ADAPTERS)})")

    key = _cache_key(cfg["provider"], cfg["model"], system, user)
    if use_cache:
        cached = _cache_get(key)
        if cached is not None:
            return cached

    last_err = None
    for attempt in range(MAX_RETRY):
        try:
            raw = adapter(cfg, system, user, temperature)
            out = _extract_json(raw)
            if use_cache:
                _cache_put(key, out)
            return out
        except FatalLLMError:
            raise  # sai key/quota/request -> DỪNG ngay, KHÔNG đốt thêm
        except Exception as e:  # noqa: BLE001 — lỗi mạng/timeout/parse -> retry
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"LLM gọi thất bại sau {MAX_RETRY} lần "
                       f"({cfg['provider']}/{cfg['model']}): {last_err}")


def active_config() -> dict:
    """Trả config hiện tại (ẩn key) — để debug 'đang dùng provider/model nào'."""
    c = _cfg()
    return {"provider": c["provider"], "model": c["model"],
            "has_openai_key": bool(c["openai_key"]),
            "has_google_key": bool(c["google_key"]),
            "has_anthropic_key": bool(c["anthropic_key"]),
            "ollama_host": c["ollama_host"]}


if __name__ == "__main__":
    print("Cấu hình LLM hiện tại (.env):")
    for k, v in active_config().items():
        print(f"  {k}: {v}")
    print("\nĐể test thật: đặt LLM_PROVIDER + key trong .env rồi chạy ABSA (Bước 5.3).")
