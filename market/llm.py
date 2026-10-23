"""Claude(Anthropic Messages API) 호출 — 표준 라이브러리 urllib 만 씁니다(이 저장소는 pip 패키지를 쓰지 않습니다).

리포트 종류와 무관하게 재사용합니다: complete_json(system, user, schema) 한 번에 구조화 JSON 을 받습니다.
- 키: 환경변수 ANTHROPIC_API_KEY. 없으면 available() 이 False 이고 호출 쪽에서 조용히 건너뜁니다.
- 모델 claude-opus-5-5, thinking 파라미터는 보내지 않음(기본 adaptive), output_config.effort = "low", max_tokens 4000.
- 429·5xx·네트워크 오류는 2회만 재시도. stop_reason 이 "refusal" 이면 data 없이 돌려줍니다.
- 반환 usage 에 input_tokens · output_tokens 를 담아 비용을 추적합니다.
"""
import json
import os
import time
import urllib.error
import urllib.request

from .http import _CTX

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MODEL = "claude-opus-5-5"
MAX_TOKENS = 4000
EFFORT = "low"
UA = "indie-trending/1.0 (https://github.com/subinlimied/indie-trending)"


def api_key():
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def available():
    return bool(api_key())


def build_body(system, user, schema, model=MODEL, max_tokens=MAX_TOKENS, effort=EFFORT):
    """요청 본문 dict. 구조화 출력(output_config.format = json_schema)으로 첫 text 블록에 JSON 이 옵니다."""
    return {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    }


def _post(body, key, timeout=180):
    req = urllib.request.Request(API_URL, data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST", headers={
        "x-api-key": key, "anthropic-version": API_VERSION, "content-type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
        return json.loads(r.read().decode("utf-8"))


def complete_json(system, user, schema, log=print, retries=2, **kw):
    """→ {"ok": bool, "data": dict|None, "usage": {"input_tokens", "output_tokens"}, "stop_reason", "error", "model"}.
    키가 없으면 ok=False, error="no_key" 로 바로 돌아옵니다(호출 없음)."""
    key = api_key()
    out = {"ok": False, "data": None, "usage": {"input_tokens": 0, "output_tokens": 0}, "stop_reason": "", "error": "", "model": kw.get("model", MODEL)}
    if not key:
        out["error"] = "no_key"
        return out
    body = build_body(system, user, schema, **kw)
    resp, last = None, ""
    for attempt in range(retries + 1):
        try:
            resp = _post(body, key)
            break
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode("utf-8", "replace")[:300]
                e.close()
            except Exception:  # noqa: BLE001
                detail = ""
            last = f"HTTP {e.code} {detail}"
            if e.code == 429 or e.code >= 500:
                if attempt < retries:
                    time.sleep(5.0 * (attempt + 1))
                    continue
            break   # 400·401·403 등은 재시도하지 않습니다
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = f"{type(e).__name__}: {e}"
            if attempt < retries:
                time.sleep(5.0 * (attempt + 1))
                continue
    if resp is None:
        out["error"] = last or "no_response"
        log(f"[llm] 실패 — {out['error'][:160]}")
        return out
    u = resp.get("usage") or {}
    out["usage"] = {"input_tokens": int(u.get("input_tokens") or 0), "output_tokens": int(u.get("output_tokens") or 0)}
    out["stop_reason"] = resp.get("stop_reason", "")
    out["model"] = resp.get("model", out["model"])
    log(f"[llm] {out['model']} · stop={out['stop_reason']} · input {out['usage']['input_tokens']} · output {out['usage']['output_tokens']} 토큰")
    if out["stop_reason"] == "refusal":
        out["error"] = "refusal"
        return out
    text = next((b.get("text", "") for b in resp.get("content") or [] if b.get("type") == "text"), "")
    try:
        out["data"] = json.loads(text)
        out["ok"] = True
    except json.JSONDecodeError as e:
        out["error"] = f"json: {e}"
        log(f"[llm] JSON 파싱 실패 — {e}")
    return out
