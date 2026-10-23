"""미디어·밈 스냅샷 → 리포트 dict (숏폼 중심).

우선순위: ① 틱톡·인스타 트렌드(KYM 네 소스에서 플랫폼 태그 TikTok/Instagram 항목) ② 새로 등록된 밈(KYM 확정·제출)
③ 커뮤니티 베스트(Reddit) ④ 유튜브 인기 급상승 Top 10(키 있을 때, 60초 이하는 "쇼츠" 표시) ⑤ 검색 급상승·위키(제외 필터 적용, 접힘)
⑥ 밈 템플릿 변동 ⑦ 게임 교차. "오늘의 트렌드 한 건"은 ①에서 고릅니다.

정치·경제·스포츠·사건사고 제외 필터(config media.exclude_keywords)는 Google 트렌드(제목+관련 뉴스 제목)·위키 제목에 겁니다.
밈 설명(한국어)·인사이트는 ANTHROPIC_API_KEY 가 있을 때 llm_request() 로 요청 본문을 만들고 attach_llm() 으로 리포트에 붙입니다(market/llm.py).
한국어 키워드는 부분 일치, 영어(ASCII) 키워드는 단어 경계 일치(rate 가 pirate 를 거르지 않게). 사람 이름은 못 거르므로 완벽하지 않습니다.
연속 일수는 reports/media/state.json 에 State 로 보관합니다: state["pick"](오늘의 트렌드), state["streaks"][소스][제목].
"""
import re
from datetime import datetime, timedelta
from pathlib import Path

from .common import State, load_snaps, round_no

PLATFORM_ORDER = ["TikTok", "Instagram", "YouTube", "Twitter/X", "Reddit", "Twitch"]
SHORTFORM = ("TikTok", "Instagram")
KYM_KEYS = ("kym_feed", "kym_search", "kym_confirmed", "kym_submissions", "kym")   # "kym" 은 첫 회차(10-22)의 옛 키
KIND_KO = {"newsfeed": "뉴스피드", "search": "검색", "confirmed": "확정 엔트리", "submissions": "제출 엔트리"}


def _src(snap, key):
    return ((snap or {}).get("sources") or {}).get(key) or {"status": "fail", "items": [], "label": key}


def _items(snap, key):
    return _src(snap, key).get("items") or []


# ---------- 제외 필터 ----------

def make_filter(cfg):
    kw = cfg.get("exclude_keywords") or {}
    subs = [k.lower() for k in kw.get("ko", []) if k and not k.isascii()] + [k.lower() for k in kw.get("ko", []) if k and k.isascii() and len(k) < 2]
    words = [k.lower() for k in kw.get("en", []) if k] + [k.lower() for k in kw.get("ko", []) if k and k.isascii() and len(k) >= 2]
    word_rx = [(k, re.compile(r"(?<![a-z0-9])" + re.escape(k) + r"(?![a-z0-9])")) for k in words]

    def hit(*texts):
        blob = " ".join(t or "" for t in texts).lower()
        for k in subs:
            if k in blob:
                return k
        for k, rx in word_rx:
            if rx.search(blob):
                return k
        return None
    return hit


# ---------- 게임 이름 사전 (data/steam · data/itch) ----------

WORD_RX = re.compile(r"[A-Za-z0-9가-힣]+")


def _latest_snap(data_dir: Path, platform, date):
    snaps = load_snaps(data_dir, platform, date, days=7)
    return snaps[-1][1] if snaps else None


def game_names(data_dir: Path, date):
    out, seen = [], set()
    steam = _latest_snap(data_dir, "steam", date)
    for appid, a in ((steam or {}).get("apps") or {}).items():
        name = (a.get("name") or "").strip()
        if len(name) >= 3 and name.lower() not in seen:
            seen.add(name.lower())
            out.append((name.lower(), name, "steam", f"https://store.steampowered.com/app/{a.get('appid') or appid}/"))
    itch = _latest_snap(data_dir, "itch", date)
    for g in ((itch or {}).get("games") or {}).values():
        name = (g.get("title") or g.get("name") or "").strip()
        if len(name) >= 3 and name.lower() not in seen:
            seen.add(name.lower())
            out.append((name.lower(), name, "itch", g.get("url") or ""))
    return out


def _allow_partial(lname):
    return len(WORD_RX.findall(lname)) >= 2 or len(lname) >= 8


def match_games(title, games):
    """완전 일치는 항상, 부분 일치는 단어 경계 + 이름이 2단어 이상이거나 8자 이상일 때만."""
    t = (title or "").lower()
    hits = []
    for lname, name, platform, url in games:
        if t == lname:
            hits.append((name, platform, url))
        elif _allow_partial(lname) and re.search(r"(?<![A-Za-z0-9가-힣])" + re.escape(lname) + r"(?![A-Za-z0-9가-힣])", t):
            hits.append((name, platform, url))
    return hits


# ---------- 연속 일수 ----------

def _streaks(state, key, titles, date, prev_date, carry=False):
    all_s = state.d.setdefault("streaks", {})
    cur = all_s.get(key) or {}
    new = {}
    for t in titles:
        rec = cur.get(t)
        if rec and rec.get("date") == date:
            new[t] = rec
        elif rec and prev_date and rec.get("date") == prev_date:
            new[t] = {"n": rec.get("n", 1) + (0 if carry else 1), "date": date}
        else:
            new[t] = {"n": 1, "date": date}
    all_s[key] = new
    return {t: v["n"] for t, v in new.items()}


def _when(x):
    """정렬 기준 = 발행 시각(없으면 수정 시각). 수정만으로 오래된 항목이 위로 오지 않게 합니다."""
    return x.get("published") or x.get("modified") or ""


def _recent(x):
    """48시간 판정 기준 = 발행·수정 중 늦은 쪽(검색으로 찾은 '갱신' 항목을 살리기 위해)."""
    return max(x.get("published") or "", x.get("modified") or "")


def kym_union(snap):
    """KYM 네 소스를 url 로 합칩니다(뉴스피드 > 검색 > 확정 > 제출 순으로 먼저 본 것을 유지, 플랫폼 태그는 합집합)."""
    out = {}
    for key in KYM_KEYS:
        for x in _items(snap, key):
            u = x.get("url")
            if not u:
                continue
            if u in out:
                for p in x.get("platforms") or []:
                    if p not in out[u]["platforms"]:
                        out[u]["platforms"].append(p)
                out[u]["kinds"].append(x.get("kind", key))
                if not out[u].get("status") and x.get("status"):
                    out[u]["status"] = x["status"]
                continue
            out[u] = {**x, "platforms": list(x.get("platforms") or []), "kinds": [x.get("kind", key)]}
    return sorted(out.values(), key=_when, reverse=True)


# ---------- 분석 ----------

def analyze(cfg, date, data_dir: Path, reports_dir: Path):
    snaps = load_snaps(data_dir, "media", date, days=35)
    today = next((s for d, s in snaps if d == date), None)
    if today is None:
        raise FileNotFoundError(f"data/media/{date}.json 없음")
    prior = [(d, s) for d, s in snaps if d < date]
    prev_date, prev = prior[-1] if prior else (None, None)
    rnd = round_no(data_dir, "media", date)
    state = State(reports_dir / "media" / "state.json")
    hit = make_filter(cfg)
    trends_top, imgflip_top = cfg.get("trends_top", 10), cfg.get("imgflip_top", 30)
    sources = today.get("sources") or {}
    filtered = {}

    # ① 틱톡·인스타 트렌드 + 플랫폼 집계
    kym_all = kym_union(today)
    prev_urls = {x["url"] for x in kym_union(prev)} if prev else set()
    for x in kym_all:
        x["new"] = bool(prev) and x["url"] not in prev_urls
    hours = (today.get("params") or {}).get("kym_hours", 48)
    try:
        cutoff = (datetime.strptime(today.get("collected_at", ""), "%Y-%m-%dT%H:%M:%SZ") - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        cutoff = ""
    shortform = [x for x in kym_all if any(p in SHORTFORM for p in x["platforms"]) and (not _recent(x) or _recent(x) >= cutoff)]
    counts = {}
    for x in kym_all:
        for p in x["platforms"]:
            counts[p] = counts.get(p, 0) + 1
    platform_counts = [(p, counts[p]) for p in PLATFORM_ORDER if p in counts]
    platform_counts += sorted(((p, n) for p, n in counts.items() if p not in PLATFORM_ORDER), key=lambda x: -x[1])

    pick = None
    for want in ("TikTok", "Instagram", None):
        cand = [x for x in shortform if want is None or want in x["platforms"]] or ([x for x in kym_all] if want is None else [])
        if cand:
            x = cand[0]
            n, since = state.bump("pick", x["url"], date, prev_date)
            reason = {"TikTok": "KYM 최신 TikTok 항목", "Instagram": "KYM 최신 Instagram 항목"}.get(want, "KYM 최신 항목 (틱톡·인스타 태그 없음)")
            pick = {**x, "streak": n, "since": since, "reason": reason}
            break

    # ② 새로 등록된 밈 (확정 · 제출)
    new_memes = [x for x in kym_all if any(k in ("confirmed", "submissions") for k in x["kinds"])]
    new_memes.sort(key=lambda x: (0 if x.get("status") == "confirmed" else 1, -(_when(x) > "")))
    new_memes.sort(key=_when, reverse=True)

    # ③ Reddit
    reddit = []
    for sub in (today.get("params") or {}).get("reddit_subs") or []:
        s = _src(today, f"reddit_{sub.lower()}")
        reddit.append({"sub": sub, "status": s.get("status"), "error": s.get("error", ""), "items": (s.get("items") or [])[:8]})

    # ④ 유튜브 인기 급상승 Top 10 (60초 이하는 shorts=True)
    youtube = {}
    for region in ("KR", "US"):
        key = f"youtube_{region.lower()}"
        s = _src(today, key)
        items = s.get("items") or []
        youtube[region] = {"status": s.get("status"), "error": s.get("error", ""), "items": items[:10], "total": len(items),
                           "shorts": sum(1 for v in items if v.get("shorts"))}

    # ⑤ 검색 급상승 · 위키 (제외 필터)
    trends = {}
    for geo in ("KR", "US"):
        key = f"trends_{geo.lower()}"
        kept, dropped = [], 0
        for x in _items(today, key):
            k = hit(x["title"], x.get("news_title"))
            if k:
                dropped += 1
                continue
            kept.append({**x, "rank": len(kept) + 1})
        st = _streaks(state, key, [x["title"] for x in kept], date, prev_date)
        trends[geo] = [{**x, "days": st.get(x["title"], 1)} for x in kept[:trends_top]]
        filtered[key] = dropped
    wiki = {}
    for proj in ("en", "ko"):
        key = f"wiki_{proj}"
        day, prev_day = _src(today, key).get("day", ""), _src(prev, key).get("day", "") if prev else ""
        same = bool(day) and day == prev_day
        prev_rank = {x["title"]: x["rank"] for x in _items(prev, key)} if prev and not same else {}
        kept, dropped = [], 0
        for x in _items(today, key):
            if hit(x["title"]):
                dropped += 1
                continue
            kept.append(x)
        st = _streaks(state, key, [x["title"] for x in kept], date, prev_date, carry=same)
        wiki[proj] = [{**x, "days": st.get(x["title"], 1), "prev_rank": prev_rank.get(x["title"])} for x in kept]
        wiki[f"{proj}_day"], wiki[f"{proj}_same"] = day, same
        filtered[key] = dropped

    # ⑥ Imgflip 순위 변동
    cur_all = _items(today, "imgflip")
    prev_all = _items(prev, "imgflip") if prev else []
    prev_rank = {x["id"]: x["rank"] for x in prev_all}
    prev_name = {x["id"]: x["name"] for x in prev_all}
    cur_ids = {x["id"] for x in cur_all}
    imgflip_items = [{**x, "prev_rank": prev_rank.get(x["id"]), "delta": (prev_rank[x["id"]] - x["rank"]) if x["id"] in prev_rank else None,
                      "new": bool(prev) and x["id"] not in prev_rank} for x in cur_all[:imgflip_top]]
    entered = [x for x in cur_all if prev and x["id"] not in prev_rank]
    exited = [{"id": i, "name": prev_name[i], "prev_rank": r} for i, r in sorted(prev_rank.items(), key=lambda kv: kv[1]) if i not in cur_ids]
    movers = sorted([x for x in imgflip_items if x["delta"]], key=lambda x: (-abs(x["delta"]), x["rank"]))
    imgflip = {"items": imgflip_items, "entered": entered, "exited": exited, "movers": movers[:10], "total": len(cur_all),
               "compared": bool(prev) and bool(prev_all)}

    # ⑦ 게임 ↔ 밈 교차 (검색 · 위키 · Reddit · 유튜브 · 숏폼 제목)
    games = game_names(data_dir, date)
    cross, seen = [], set()

    def _cross(title, source, url):
        for name, platform, gurl in match_games(title, games):
            k = (name.lower(), source)
            if k in seen:
                continue
            seen.add(k)
            cross.append({"term": title, "source": source, "game": name, "platform": platform, "game_url": gurl, "url": url})

    for x in shortform:
        _cross(x["title"], "KYM", x["url"])
    for geo in ("KR", "US"):
        for x in trends[geo]:
            _cross(x["title"], f"검색 {geo}", x.get("url", ""))
    for proj in ("en", "ko"):
        for x in wiki[proj]:
            _cross(x["title"], f"위키 {proj}", x.get("url", ""))
    for r in reddit:
        for x in r["items"]:
            _cross(x["title"], f"r/{r['sub']}", x.get("url", ""))
    for region in ("KR", "US"):
        for v in youtube[region]["items"]:
            _cross(v["title"], f"유튜브 {region}", v.get("url", ""))

    # 수집 상태
    status_rows = []
    for key, s in sources.items():
        status_rows.append({"key": key, "label": s.get("label", key), "status": s.get("status"), "count": s.get("count", 0),
                            "error": s.get("error", ""), "filtered": filtered.get(key, 0)})
    ok = sum(1 for s in status_rows if s["status"] == "ok")
    skipped = sum(1 for s in status_rows if s["status"] == "skip")
    failed = [s["label"] for s in status_rows if s["status"] == "fail"]
    reddit_ok = [r["sub"] for r in reddit if r["status"] == "ok"]
    n_filtered = sum(filtered.values())
    collect_line = (f"소스 {ok}/{len(status_rows) - skipped} 정상" + (f" · 건너뜀 {skipped}" if skipped else "")
                    + f" · KYM {len(kym_all)}건(틱톡·인스타 {len(shortform)}) · 새 밈 {len(new_memes)} · Reddit {len(reddit_ok)}/{len(reddit)}"
                    + f" · 검색 {len(trends['KR'])}/{len(trends['US'])} · 위키 {len(wiki['en'])}/{len(wiki['ko'])}"
                    + f" · 제외 필터 {n_filtered}건")
    if failed:
        collect_line += " · 실패: " + ", ".join(failed)
    state.save()
    status = [["회차", f"{rnd}회차"], ["비교 대상", f"{prev_date} · 1일치" if prev_date else "없음"],
              ["틱톡·인스타", f"{len(shortform)}건 / KYM {len(kym_all)}"], ["새 밈", f"{len(new_memes)}건"],
              ["제외 필터", f"{n_filtered}건"], ["게임 교차", f"{len(cross)}건"],
              ["수집", (today.get("collected_at") or "").replace("T", " ").replace("Z", " UTC")]]
    return {
        "kind": "media", "platform": "media", "platform_ko": "미디어·밈", "date": date, "round": rnd, "prev_date": prev_date,
        "status": status, "collect_line": collect_line,
        "basis_line": (f"KYM 뉴스피드·확정·제출 RSS + 검색 tiktok/instagram/reels (최근 {hours}시간) · Reddit top(t=day) 8개 × {len(reddit)}개 서브레딧 · "
                       f"YouTube 인기 급상승 KR·US Top 10(60초 이하는 쇼츠 표시, 키 있을 때) · Google 트렌드 일간 KR·US · 위키백과 조회수 상위 en·ko · "
                       f"Imgflip 인기 템플릿 100개 중 상위 {imgflip_top} · 제외 필터 = config media.exclude_keywords (정치·경제·스포츠·사건사고, 사람 이름은 못 거름) · "
                       f"게임 교차 = Steam·itch 스냅샷 게임 이름과 대조"),
        "pick": pick, "platform_counts": platform_counts, "shortform": shortform, "kym_all": kym_all,
        "kym_new": sum(1 for x in kym_all if x["new"]), "new_memes": new_memes, "reddit": reddit, "youtube": youtube,
        "trends": trends, "wiki": wiki, "imgflip": imgflip, "cross": cross, "filtered": filtered, "sources": status_rows,
    }


# ---------- 밈 설명(한국어) · 인사이트: Claude 요청 본문과 결합 ----------

LLM_SYSTEM = """당신은 밈·숏폼 트렌드를 게임 제작자에게 설명하는 한국어 편집자입니다. 독자는 모바일 게임 UI 디자이너이며 혼자 만들 인디게임과 콘텐츠 소재를 찾고 있습니다.

한국어 문장 규칙:
- 조사와 어미를 생략하지 않고 완결된 문장으로 씁니다. 명사만 나열하지 않습니다.
- 엠대시(—)를 쓰지 않습니다. 과장하거나 단정하지 않고, 추측은 "~로 보입니다"처럼 추측임을 밝힙니다.
- 밈 이름, 플랫폼 이름, 계정 이름은 원어 그대로 둡니다.
- 숫자를 반복해서 나열하지 않습니다.
- 각 밈 설명(ko_what)은 두세 문장으로, 무엇인지·어디서 시작됐는지·어떻게 쓰이는지를 적습니다. 자료에 없는 사실을 지어내지 않습니다.
- ko_idea 는 게임이나 콘텐츠 소재로 쓸 아이디어 한 문장입니다.
- insight 는 리포트 전체를 보고 쓰는 한 문단(4~6문장)입니다. 대중문화·숏폼·과거 성공작의 계보와 연결하고, 추측은 추측이라고 표시합니다."""

LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "memes": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "ko_what": {"type": "string"}, "ko_idea": {"type": "string"}},
            "required": ["id", "ko_what", "ko_idea"], "additionalProperties": False}},
        "insight": {"type": "string"},
    },
    "required": ["memes", "insight"], "additionalProperties": False,
}


def llm_targets(rep, limit=12):
    """설명 대상 = 01 틱톡·인스타 + 02 새 밈 (url 로 중복 제거, 최대 limit)."""
    out, seen = [], set()
    for x in list(rep.get("shortform") or []) + list(rep.get("new_memes") or []):
        if x["url"] in seen:
            continue
        seen.add(x["url"])
        out.append(x)
        if len(out) >= limit:
            break
    return out


def llm_request(rep):
    """→ (system, user) 문자열. 하루 1회: 밈 설명 전부 + 인사이트를 한 요청에서 JSON 으로 받습니다."""
    targets = llm_targets(rep)
    lines = [f"날짜: {rep['date']} · {rep['round']}회차", "", "## 설명할 밈 (id 는 그대로 돌려주십시오)"]
    for i, x in enumerate(targets, 1):
        lines.append(f"### id={x['url']}")
        lines.append(f"제목: {x['title']}")
        if x.get("platforms"):
            lines.append("플랫폼 단서: " + ", ".join(x["platforms"]))
        if x.get("status"):
            lines.append(f"KYM 상태: {x['status']}")
        lines.append("About: " + (x.get("about") or x.get("summary") or "(자료 없음)"))
        lines.append("")
    lines.append("## 리포트 요약 (insight 용)")
    lines.append("플랫폼 집계: " + (", ".join(f"{a} {n}건" for a, n in rep.get("platform_counts") or []) or "없음"))
    for r in rep.get("reddit") or []:
        if r["status"] == "ok" and r["items"]:
            lines.append(f"r/{r['sub']} 상위: " + " / ".join(x["title"][:80] for x in r["items"][:3]))
    for region in ("KR", "US"):
        y = (rep.get("youtube") or {}).get(region) or {}
        if y.get("status") == "ok" and y.get("items"):
            lines.append(f"유튜브 인기 {region}: " + " / ".join(f"{v['title'][:60]}{' (쇼츠)' if v.get('shorts') else ''}" for v in y["items"][:5]))
    for geo in ("KR", "US"):
        t = (rep.get("trends") or {}).get(geo) or []
        if t:
            lines.append(f"검색 급상승 {geo}: " + " / ".join(x["title"] for x in t[:5]))
    im = rep.get("imgflip") or {}
    if im.get("compared"):
        lines.append("밈 템플릿 변동: " + (" / ".join(f"{x['name']} {x['prev_rank']}→{x['rank']}위" for x in im.get("movers", [])[:5]) or "상위 30 변동 없음"))
    if rep.get("cross"):
        lines.append("게임 교차: " + " / ".join(f"{c['term'][:50]} → {c['game']}" for c in rep["cross"][:5]))
    lines.append("")
    lines.append("위 자료만 근거로 memes 배열(각 id 마다 ko_what, ko_idea)과 insight 를 한국어로 작성하십시오.")
    return LLM_SYSTEM, "\n".join(lines)


def attach_llm(rep, result):
    """complete_json 결과를 리포트에 붙입니다: 항목별 ko_what·ko_idea, rep["insight"], rep["llm_usage"]."""
    rep["llm_usage"] = {**(result.get("usage") or {}), "model": result.get("model", ""), "stop_reason": result.get("stop_reason", ""),
                        "error": result.get("error", ""), "ok": bool(result.get("ok"))}
    data = result.get("data") or {}
    if not result.get("ok") or not isinstance(data, dict):
        return 0
    by_id = {m.get("id"): m for m in data.get("memes") or [] if isinstance(m, dict)}
    n = 0
    for key in ("shortform", "new_memes", "kym_all"):
        for x in rep.get(key) or []:
            m = by_id.get(x["url"])
            if m and (m.get("ko_what") or m.get("ko_idea")):
                x["ko_what"], x["ko_idea"] = (m.get("ko_what") or "").strip(), (m.get("ko_idea") or "").strip()
                n += key == "kym_all"
    p = rep.get("pick")
    if p and by_id.get(p["url"]):
        p["ko_what"], p["ko_idea"] = (by_id[p["url"]].get("ko_what") or "").strip(), (by_id[p["url"]].get("ko_idea") or "").strip()
    rep["insight"] = (data.get("insight") or "").strip()
    return n
