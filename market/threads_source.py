"""Threads 키워드 관찰 수집기 + 장기 토큰 관리 (표준 라이브러리만).

Meta Threads API `GET /v1.0/keyword_search` (graph.threads.net, q · search_type TOP/RECENT · fields · limit 최대 100)로
config.json `media.threads.keywords` 의 키워드마다 TOP 과 RECENT 를 한 번씩 조회합니다. 문서 기준 한 사용자가 24시간에 2,200회까지라
키워드 30개 × 2 유형 × 페이지 1 = 60회 안팎으로 끝나며, `max_calls` 로 상한을 둡니다.

토큰: 환경 변수 THREADS_ACCESS_TOKEN(장기 토큰, 60일). 없으면 조용히 건너뛰고 "토큰 없음" 메모만 남깁니다.
매 실행마다 `GET /v1.0/debug_token` 으로 만료일을 확인하고, 만료가 `refresh_days` 일 이내이면서 토큰이 24시간 이상 지났으면
`GET /refresh_access_token?grant_type=th_refresh_token` 으로 갱신합니다. 새 토큰은 REPO_SECRETS_PAT(Secrets 쓰기 권한 fine-grained PAT)가
있을 때만 `gh secret set THREADS_ACCESS_TOKEN` 으로 저장하고, 없으면 리포트 메모로 "N일 뒤 만료" 를 남깁니다.
토큰 값은 로그·스냅샷·예외 메시지 어디에도 쓰지 않습니다(_redact).
"""
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from . import http

API = "https://graph.threads.net/v1.0"
API_ROOT = "https://graph.threads.net"
FIELDS = "id,text,media_type,permalink,timestamp,username,has_replies,is_quote_post,is_reply"
TOKEN_ENV = "THREADS_ACCESS_TOKEN"
PAT_ENV = "REPO_SECRETS_PAT"
SECRET_NAME = "THREADS_ACCESS_TOKEN"
DEFAULT_REPO = "subinlimied/indie-trending"
TEXT_LEN = 300
DAY_LIMIT = 2200           # 문서: 사용자당 24시간 2,200회 (앱 구분 없음, 결과 0건은 미산정)

DEFAULT_KEYWORDS = [
    "인디게임", "게임개발", "1인개발", "유니티", "고도엔진", "스팀 신작", "픽셀아트", "로그라이크", "게임잼", "방치형 게임",
    "밈", "릴스", "챌린지", "숏폼",
    "indie game", "gamedev", "solo dev", "pixel art", "roguelike", "steam next fest", "itch.io", "game jam",
    "cozy game", "horror game", "wishlist", "devlog", "unity3d", "godot", "screenshotsaturday", "gameart",
]
DEFAULTS = {"keywords": DEFAULT_KEYWORDS, "limit": 100, "pages": 1, "max_calls": 200, "refresh_days": 14, "sleep": 0.4, "hours": 24}


def settings(cfg_threads):
    out = dict(DEFAULTS)
    out.update({k: v for k, v in (cfg_threads or {}).items() if v is not None})
    out["keywords"] = [k.strip() for k in out.get("keywords") or [] if k and k.strip()]
    out["limit"] = max(1, min(int(out["limit"]), 100))
    out["pages"] = max(1, int(out["pages"]))
    return out


# ---------- 토큰 값 가리기 ----------

_SECRETS = []


def _redact(s):
    s = str(s or "")
    for t in _SECRETS:
        if t and t in s:
            s = s.replace(t, "***")
    return re.sub(r"access_token=[^&\s\"']+", "access_token=***", s)


def _remember(token):
    if token and token not in _SECRETS:
        _SECRETS.append(token)


# ---------- HTTP (토큰이 URL 에 들어가므로 http.get 의 예외 문구를 그대로 쓰지 않습니다) ----------

def _api_get(path, params, retries=1, timeout=25):
    url = (API_ROOT if path.startswith("/") else API + "/") + path.lstrip("/") + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": http.UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout, context=http._CTX) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:  # noqa: BLE001
                body = ""
            try:
                e.close()
            except Exception:  # noqa: BLE001
                pass
            msg = ""
            try:
                err = (json.loads(body) or {}).get("error") or {}
                msg = f"{err.get('type', '')} {err.get('code', '')}: {err.get('message', '')}".strip()
            except (json.JSONDecodeError, AttributeError):
                msg = body[:120]
            last = RuntimeError(f"HTTP {e.code} {_redact(msg)[:160]}")
            if e.code in (429,) or e.code >= 500:
                time.sleep(3.0 * (attempt + 1))
                continue
            raise last
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = RuntimeError(_redact(f"{type(e).__name__}: {e}")[:160])
            time.sleep(2.0 * (attempt + 1))
    raise last or RuntimeError("요청 실패")


# ---------- 토큰 상태 · 갱신 · Secrets 저장 ----------

def token_status(token, now=None):
    """debug_token → 만료일·남은 일수·권한. 실패하면 checked=False 와 이유만."""
    now = now or datetime.now(timezone.utc)
    try:
        data = _api_get("debug_token", {"input_token": token, "access_token": token})
    except Exception as e:  # noqa: BLE001
        return {"checked": False, "error": _redact(e)[:160]}
    d = (data or {}).get("data") or {}
    exp = d.get("expires_at") or 0
    issued = d.get("issued_at") or 0
    scopes = d.get("scopes") or []
    out = {"checked": True, "valid": bool(d.get("is_valid")), "scopes": scopes,
           "keyword_scope": "threads_keyword_search" in scopes}
    if exp:
        exp_dt = datetime.fromtimestamp(exp, timezone.utc)
        out["expires_at"] = exp_dt.strftime("%Y-%m-%d")
        out["days_left"] = max(0, int((exp_dt - now).total_seconds() // 86400))
    if issued:
        out["age_days"] = round((now - datetime.fromtimestamp(issued, timezone.utc)).total_seconds() / 86400, 1)
    if d.get("error"):
        out["error"] = _redact(d["error"].get("message", ""))[:160]
    return out


def refresh_token(token):
    data = _api_get("/refresh_access_token", {"grant_type": "th_refresh_token", "access_token": token})
    new = (data or {}).get("access_token")
    if not new:
        raise RuntimeError("응답에 access_token 없음")
    _remember(new)
    return new, int((data or {}).get("expires_in") or 0)


def save_secret(new_token, pat, repo=None, name=SECRET_NAME):
    """gh secret set <name> --repo <repo> (값은 stdin). 반환 (ok, 메시지). 메시지에 토큰은 들어가지 않습니다."""
    repo = repo or os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO
    env = {k: v for k, v in os.environ.items() if k not in (PAT_ENV, TOKEN_ENV)}
    env["GH_TOKEN"] = pat
    try:
        r = subprocess.run(["gh", "secret", "set", name, "--repo", repo], input=new_token, env=env,
                           capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return False, "gh CLI 없음"
    except subprocess.TimeoutExpired:
        return False, "gh 시간 초과"
    if r.returncode != 0:
        return False, _redact((r.stderr or r.stdout or "").strip())[:160]
    return True, f"{repo} 의 {name} 갱신"


def maintain_token(cfg, log=print, now=None):
    """환경 변수의 토큰을 점검·갱신합니다. 반환 dict 에는 토큰 값이 없고, 실제로 쓸 토큰은 "_token" 키(저장 전 제거)에 둡니다."""
    now = now or datetime.now(timezone.utc)
    token = (os.environ.get(TOKEN_ENV) or "").strip()
    if not token:
        return {"present": False, "note": "Threads: 토큰 없음"}
    _remember(token)
    info = {"present": True, "_token": token, "refreshed": False, "secret_saved": False, "note": ""}
    st = token_status(token, now)
    info.update({k: v for k, v in st.items() if k != "scopes"})
    info["scopes"] = st.get("scopes", [])
    if not st.get("checked"):
        info["note"] = f"Threads 토큰 상태 확인 실패 ({st.get('error', '')})"
        log(f"[media] Threads 토큰: 상태 확인 실패 — {st.get('error', '')}")
        return info
    if not st.get("valid"):
        info["note"] = "Threads 토큰이 만료되었거나 유효하지 않습니다. README 절차대로 다시 넣어 주세요"
        log("[media] Threads 토큰: 유효하지 않음")
        return info
    days = st.get("days_left")
    log(f"[media] Threads 토큰: 정상 · 만료 {st.get('expires_at', '?')} ({days}일 남음) · keyword_search 권한 {'있음' if st.get('keyword_scope') else '없음'}")
    if not st.get("keyword_scope"):
        info["note"] = "Threads 토큰에 threads_keyword_search 권한이 없습니다"
    if days is None or days > cfg["refresh_days"]:
        return info
    if (st.get("age_days") or 0) < 1.0:
        info["note"] = f"Threads 토큰이 {days}일 뒤 만료됩니다 (발급 24시간 전이라 아직 갱신 불가)"
        return info
    try:
        new, expires_in = refresh_token(token)
    except Exception as e:  # noqa: BLE001
        info["note"] = f"Threads 토큰이 {days}일 뒤 만료됩니다. 갱신 실패({_redact(e)[:80]}) — README 절차대로 다시 넣어 주세요"
        log(f"[media] Threads 토큰: 갱신 실패 — {_redact(e)}")
        return info
    info["refreshed"] = True
    info["_token"] = new
    new_exp = (now + timedelta(seconds=expires_in)).strftime("%Y-%m-%d") if expires_in else "?"
    info["new_expires_at"] = new_exp
    pat = (os.environ.get(PAT_ENV) or "").strip()
    if pat:
        ok, msg = save_secret(new, pat)
        info["secret_saved"] = ok
        info["note"] = (f"Threads 토큰을 갱신해 Secrets 에 저장했습니다 (새 만료 {new_exp})" if ok
                        else f"Threads 토큰을 갱신했지만 Secrets 저장 실패({msg}). {days}일 뒤 만료 — README 절차대로 다시 넣어 주세요")
        log(f"[media] Threads 토큰: 갱신 · Secrets 저장 {'성공' if ok else '실패 — ' + msg}")
    else:
        info["note"] = f"Threads 토큰이 {days}일 뒤 만료됩니다. README 절차대로 다시 넣어 주세요 (REPO_SECRETS_PAT 가 있으면 자동 저장)"
        log(f"[media] Threads 토큰: 갱신했지만 {PAT_ENV} 가 없어 저장 못 함 — {days}일 뒤 만료")
    return info


# ---------- 키워드 검색 ----------

def _iso(ts):
    """'2023-10-17T05:42:03+0000' → '2023-10-17T05:42:03Z'."""
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return datetime.strptime(ts, fmt).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        except (TypeError, ValueError):
            continue
    return ts or ""


def _norm(p):
    text = re.sub(r"\s+", " ", (p.get("text") or "")).strip()
    if len(text) > TEXT_LEN:
        text = text[: TEXT_LEN - 1].rstrip() + "…"
    return {"id": str(p.get("id") or ""), "text": text, "username": p.get("username") or "", "timestamp": _iso(p.get("timestamp")),
            "permalink": p.get("permalink") or "", "media_type": p.get("media_type") or "",
            "is_reply": bool(p.get("is_reply")), "is_quote_post": bool(p.get("is_quote_post")), "has_replies": bool(p.get("has_replies"))}


def search(token, q, search_type="TOP", limit=100, pages=1, sleep=0.4):
    """→ (정규화한 글 목록, 호출 수). paging.cursors.after 가 오면 pages 까지 이어 받습니다."""
    out, calls, after = [], 0, None
    for _ in range(pages):
        params = {"q": q, "search_type": search_type, "fields": FIELDS, "limit": limit, "access_token": token}
        if after:
            params["after"] = after
        data = _api_get("keyword_search", params)
        calls += 1
        time.sleep(sleep)
        if not isinstance(data, dict) or "data" not in data:
            raise RuntimeError(f"응답 형식 오류: {_redact(json.dumps(data, ensure_ascii=False))[:100]}")
        out += [_norm(p) for p in data.get("data") or [] if p.get("id")]
        after = ((data.get("paging") or {}).get("cursors") or {}).get("after")
        if not after or not data.get("data"):
            break
    return out, calls


def collect(cfg_threads, log=print, now=None):
    """config media.threads → 스냅샷 "threads" 블록. 토큰이 없으면 status "skip"."""
    cfg = settings(cfg_threads)
    now = now or datetime.now(timezone.utc)
    out = {"status": "skip", "error": "", "collected_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "keywords": cfg["keywords"],
           "params": {"limit": cfg["limit"], "pages": cfg["pages"], "hours": cfg["hours"]}, "calls": 0,
           "results": {}, "posts": {}, "failed": [], "token": {"present": False}}
    tok = maintain_token(cfg, log, now)
    token = tok.pop("_token", "")
    out["token"] = tok
    if not token:
        out["error"] = "THREADS_ACCESS_TOKEN 없음"
        log("[media] Threads 키워드: 건너뜀 — 토큰 없음")
        return out
    if tok.get("checked") and not tok.get("valid"):
        out["status"], out["error"] = "fail", "토큰이 유효하지 않음"
        return out
    if not cfg["keywords"]:
        out["status"], out["error"] = "fail", "키워드 목록이 비어 있음"
        return out
    t0 = time.time()
    for kw in cfg["keywords"]:
        res = {"top": [], "recent": [], "error": ""}
        for st in ("TOP", "RECENT"):
            if out["calls"] >= cfg["max_calls"]:
                res["error"] = f"호출 상한 {cfg['max_calls']} 도달"
                break
            try:
                posts, n = search(token, kw, st, cfg["limit"], cfg["pages"], cfg["sleep"])
            except Exception as e:  # noqa: BLE001  키워드 하나가 실패해도 계속
                out["calls"] += 1
                msg = _redact(e)[:160]
                res["error"] = msg
                out["failed"].append({"keyword": kw, "type": st, "error": msg})
                continue
            out["calls"] += n
            ids = []
            for p in posts:
                out["posts"].setdefault(p["id"], p)
                if p["id"] not in ids:
                    ids.append(p["id"])
            res[st.lower()] = ids
        out["results"][kw] = res
    ok_kw = sum(1 for r in out["results"].values() if not r["error"] or r["top"] or r["recent"])
    out["status"] = "ok" if ok_kw else "fail"
    if not ok_kw:
        out["error"] = (out["failed"][0]["error"] if out["failed"] else "결과 없음")
    log(f"[media] Threads 키워드: {ok_kw}/{len(cfg['keywords'])}개 정상 · 글 {len(out['posts'])}건 · 호출 {out['calls']}회 · {time.time() - t0:.1f}초"
        + (f" · 실패 {len(out['failed'])}" if out["failed"] else ""))
    return out
