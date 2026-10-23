"""미디어·밈 스냅샷 → 리포트 dict (숏폼 중심).

우선순위: ① 틱톡·인스타 트렌드(KYM 네 소스에서 플랫폼 태그 TikTok/Instagram 항목) ② 새로 등록된 밈(KYM 확정·제출)
③ 커뮤니티 베스트(Reddit) ④ X 트렌드(trends24) ⑤ 유튜브 쇼츠(키 있을 때) ⑥ 검색 급상승·위키(제외 필터 적용, 접힘)
⑦ 밈 템플릿 변동 ⑧ 게임 교차. "오늘의 트렌드 한 건"은 ①에서 고릅니다.

정치·경제·스포츠·사건사고 제외 필터(config media.exclude_keywords)는 Google 트렌드(제목+관련 뉴스 제목)·위키 제목·X 트렌드에 겁니다.
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
    shortform = [x for x in kym_all if any(p in SHORTFORM for p in x["platforms"]) and (not _when(x) or _when(x) >= cutoff)]
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

    # ④ X 트렌드 (제외 필터)
    x_trends = {}
    for region in ("KR", "WORLD"):
        key = f"x_{region.lower()}"
        kept, dropped = [], 0
        for x in _items(today, key):
            k = hit(x["title"])
            if k:
                dropped += 1
                continue
            kept.append({**x, "rank": len(kept) + 1})
        st = _streaks(state, key, [x["title"] for x in kept], date, prev_date)
        x_trends[region] = [{**x, "days": st.get(x["title"], 1)} for x in kept[:trends_top]]
        x_trends[f"{region}_at"] = _src(today, key).get("at", "")
        filtered[key] = dropped

    # ⑤ 유튜브 쇼츠
    youtube = {}
    for region in ("KR", "US"):
        key = f"youtube_{region.lower()}"
        s = _src(today, key)
        shorts = sorted([v for v in s.get("items") or [] if v.get("shorts")], key=lambda v: -v.get("views", 0))
        youtube[region] = {"status": s.get("status"), "error": s.get("error", ""), "items": shorts[:10], "total": len(s.get("items") or [])}

    # ⑥ 검색 급상승 · 위키 (제외 필터)
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

    # ⑦ Imgflip 순위 변동
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

    # ⑧ 게임 ↔ 밈 교차 (검색 · 위키 · Reddit · X · 쇼츠 · 숏폼 제목)
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
    for region in ("KR", "WORLD"):
        for x in x_trends[region]:
            _cross(x["title"], f"X {region}", x.get("url", ""))
    for region in ("KR", "US"):
        for v in youtube[region]["items"]:
            _cross(v["title"], f"쇼츠 {region}", v.get("url", ""))

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
                    + f" · X {len(x_trends['KR'])}/{len(x_trends['WORLD'])} · 검색 {len(trends['KR'])}/{len(trends['US'])} · 위키 {len(wiki['en'])}/{len(wiki['ko'])}"
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
                       f"X 트렌드 trends24.in 한국·worldwide · YouTube 인기 중 60초 이하(키 있을 때) · Google 트렌드 일간 KR·US · 위키백과 조회수 상위 en·ko · "
                       f"Imgflip 인기 템플릿 100개 중 상위 {imgflip_top} · 제외 필터 = config media.exclude_keywords (정치·경제·스포츠·사건사고, 사람 이름은 못 거름) · "
                       f"게임 교차 = Steam·itch 스냅샷 게임 이름과 대조"),
        "pick": pick, "platform_counts": platform_counts, "shortform": shortform, "kym_all": kym_all,
        "kym_new": sum(1 for x in kym_all if x["new"]), "new_memes": new_memes, "reddit": reddit, "x": x_trends, "youtube": youtube,
        "trends": trends, "wiki": wiki, "imgflip": imgflip, "cross": cross, "filtered": filtered, "sources": status_rows,
    }
