"""미디어·밈 스냅샷 → 리포트 dict. 전날 대비(Imgflip 순위 · 연속 일수 · KYM 신규), 게임 ↔ 밈 교차, 플랫폼 집계.

연속 일수는 reports/media/state.json 에 State 로 보관합니다:
  state["pick"]                  오늘의 트렌드 한 건의 연속 선정 (State.bump)
  state["streaks"][소스][제목]   Google 트렌드·위키 항목의 "n일 연속" (직전 회차에도 있었으면 +1)
"""
import json
import re
from pathlib import Path

from .common import State, load_snaps, round_no

PLATFORM_ORDER = ["TikTok", "Twitter/X", "Reddit", "YouTube", "Instagram", "Twitch"]


def _src(snap, key):
    return (snap.get("sources") or {}).get(key) or {"status": "fail", "items": [], "label": key}


def _items(snap, key):
    return _src(snap, key).get("items") or []


# ---------- 게임 이름 사전 (data/steam · data/itch) ----------

WORD_RX = re.compile(r"[A-Za-z0-9가-힣]+")


def _latest_snap(data_dir: Path, platform, date):
    snaps = load_snaps(data_dir, platform, date, days=7)
    return snaps[-1][1] if snaps else None


def game_names(data_dir: Path, date):
    """[(소문자 이름, 원래 이름, 플랫폼, url)] — 3글자 이상만."""
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
    """제목(소문자 비교) 과 겹치는 게임. 완전 일치는 항상, 부분 일치는 단어 경계 + 이름이 2단어 이상이거나 8자 이상일 때만."""
    t = (title or "").lower()
    hits = []
    for lname, name, platform, url in games:
        if t == lname:
            hits.append((name, platform, url))
        elif _allow_partial(lname) and re.search(r"(?<![A-Za-z0-9가-힣])" + re.escape(lname) + r"(?![A-Za-z0-9가-힣])", t):
            hits.append((name, platform, url))
    return hits


# ---------- 분석 ----------

def _streaks(state, key, titles, date, prev_date, carry=False):
    """titles 각각의 연속 일수. 직전 회차(prev_date)에 기록이 있으면 +1, 오늘 다시 돌리면 유지, 아니면 1.
    carry=True 면(같은 집계를 다시 받은 날) 직전 값을 올리지 않고 그대로 가져옵니다."""
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


def analyze(cfg, date, data_dir: Path, reports_dir: Path):
    snaps = load_snaps(data_dir, "media", date, days=35)
    today = next((s for d, s in snaps if d == date), None)
    if today is None:
        raise FileNotFoundError(f"data/media/{date}.json 없음")
    prior = [(d, s) for d, s in snaps if d < date]
    prev_date, prev = prior[-1] if prior else (None, None)
    rnd = round_no(data_dir, "media", date)
    state = State(reports_dir / "media" / "state.json")

    trends_top = cfg.get("trends_top", 10)
    imgflip_top = cfg.get("imgflip_top", 30)
    sources = today.get("sources") or {}

    # 1. KYM: 플랫폼 집계 · 신규 기사 · 오늘의 트렌드 한 건
    kym = _items(today, "kym")
    prev_kym_urls = {x.get("url") for x in _items(prev, "kym")} if prev else set()
    kym_items = []
    for x in kym:
        kym_items.append({**x, "new": bool(prev) and x.get("url") not in prev_kym_urls})
    counts = {}
    for x in kym:
        for p in x.get("platforms") or []:
            counts[p] = counts.get(p, 0) + 1
    platform_counts = [(p, counts[p]) for p in PLATFORM_ORDER if p in counts]
    platform_counts += sorted(((p, n) for p, n in counts.items() if p not in PLATFORM_ORDER), key=lambda x: -x[1])

    pick = None
    cand = [x for x in kym_items if "TikTok" in (x.get("platforms") or [])] or kym_items
    if cand:
        x = cand[0]
        n, since = state.bump("pick", x["url"], date, prev_date)
        pick = {**x, "streak": n, "since": since, "reason": "KYM 최신 TikTok 기사" if "TikTok" in (x.get("platforms") or []) else "KYM 최신 기사"}

    # 2. Google 트렌드 KR/US (n일 연속)
    trends = {}
    for geo in ("KR", "US"):
        key = f"trends_{geo.lower()}"
        items = _items(today, key)[:trends_top]
        st = _streaks(state, key, [x["title"] for x in items], date, prev_date)
        trends[geo] = [{**x, "days": st.get(x["title"], 1)} for x in items]

    # 3. 위키 en/ko (n일 연속 · 순위 변동)
    wiki = {}
    for proj in ("en", "ko"):
        key = f"wiki_{proj}"
        items = _items(today, key)
        day, prev_day = _src(today, key).get("day", ""), _src(prev, key).get("day", "") if prev else ""
        same = bool(day) and day == prev_day          # 집계가 아직 안 올라와 같은 날짜를 다시 받은 경우
        prev_rank = {x["title"]: x["rank"] for x in _items(prev, key)} if prev and not same else {}
        st = _streaks(state, key, [x["title"] for x in items], date, prev_date, carry=same)
        wiki[proj] = [{**x, "days": st.get(x["title"], 1), "prev_rank": prev_rank.get(x["title"])} for x in items]
        wiki[f"{proj}_day"] = day
        wiki[f"{proj}_same"] = same

    # 4. Reddit
    reddit = []
    for sub in (today.get("params") or {}).get("reddit_subs") or []:
        s = _src(today, f"reddit_{sub.lower()}")
        reddit.append({"sub": sub, "status": s.get("status"), "error": s.get("error", ""), "items": (s.get("items") or [])[:8]})

    # 5. Imgflip 순위 변동
    cur_all = _items(today, "imgflip")
    prev_all = _items(prev, "imgflip") if prev else []
    prev_rank = {x["id"]: x["rank"] for x in prev_all}
    prev_name = {x["id"]: x["name"] for x in prev_all}
    cur_ids = {x["id"] for x in cur_all}
    imgflip_items = []
    for x in cur_all[:imgflip_top]:
        pr = prev_rank.get(x["id"])
        imgflip_items.append({**x, "prev_rank": pr, "delta": (pr - x["rank"]) if pr is not None else None,
                              "new": bool(prev) and pr is None})
    entered = [x for x in cur_all if prev and x["id"] not in prev_rank]
    exited = [{"id": i, "name": prev_name[i], "prev_rank": r} for i, r in sorted(prev_rank.items(), key=lambda kv: kv[1]) if i not in cur_ids]
    movers = sorted([x for x in imgflip_items if x["delta"]], key=lambda x: (-abs(x["delta"]), x["rank"]))
    imgflip = {"items": imgflip_items, "entered": entered, "exited": exited, "movers": movers[:10],
               "total": len(cur_all), "compared": bool(prev) and bool(prev_all)}

    # 6. 게임 ↔ 밈 교차
    games = game_names(data_dir, date)
    cross, seen = [], set()

    def _cross(title, source, url):
        for name, platform, gurl in match_games(title, games):
            k = (name.lower(), source)
            if k in seen:
                continue
            seen.add(k)
            cross.append({"term": title, "source": source, "game": name, "platform": platform, "game_url": gurl, "url": url})

    for geo in ("KR", "US"):
        for x in _items(today, f"trends_{geo.lower()}"):
            _cross(x["title"], f"검색 {geo}", x.get("url", ""))
    for proj in ("en", "ko"):
        for x in _items(today, f"wiki_{proj}"):
            _cross(x["title"], f"위키 {proj}", x.get("url", ""))
    for r in reddit:
        for x in r["items"]:
            _cross(x["title"], f"r/{r['sub']}", x.get("url", ""))

    # 7. 수집 상태
    status_rows = []
    ok = 0
    for key, s in sources.items():
        status_rows.append({"key": key, "label": s.get("label", key), "status": s.get("status"), "count": s.get("count", 0), "error": s.get("error", "")})
        ok += s.get("status") == "ok"
    total = len(sources)
    failed = [s["label"] for s in status_rows if s["status"] != "ok"]
    collect_line = f"소스 {ok}/{total} 정상 · KYM {len(kym)}건 · 검색 KR {len(trends['KR'])} · US {len(trends['US'])} · 위키 en {len(wiki['en'])} · ko {len(wiki['ko'])} · Reddit {sum(1 for r in reddit if r['status'] == 'ok')}/{len(reddit)} · Imgflip {len(cur_all)}"
    if failed:
        collect_line += " · 실패: " + ", ".join(failed)

    state.save()
    status = [["회차", f"{rnd}회차"], ["비교 대상", f"{prev_date} · 1일치" if prev_date else "없음"],
              ["KYM 기사", f"{len(kym)}건 (48시간)"], ["플랫폼", " · ".join(f"{p} {n}" for p, n in platform_counts) or "—"],
              ["게임 교차", f"{len(cross)}건"], ["수집", (today.get("collected_at") or "").replace("T", " ").replace("Z", " UTC")]]
    return {
        "kind": "media", "platform": "media", "platform_ko": "미디어·밈", "date": date, "round": rnd, "prev_date": prev_date,
        "status": status, "collect_line": collect_line,
        "basis_line": (f"KYM 뉴스피드(최근 {(today.get('params') or {}).get('kym_hours', 48)}시간) · Google 트렌드 일간 KR·US Top {trends_top} · "
                       f"위키백과 전날 조회수 상위 en·ko {len(wiki['en'])}개(대문·특수·프로젝트 문서 제외) · Reddit top(t=day) 8개 × {len(reddit)}개 서브레딧 · "
                       f"Imgflip 인기 템플릿 100개 중 상위 {imgflip_top} · 게임 교차 = Steam·itch 스냅샷 게임 이름과 대조"),
        "pick": pick, "platform_counts": platform_counts, "kym": kym_items, "kym_new": sum(1 for x in kym_items if x["new"]),
        "trends": trends, "wiki": wiki, "reddit": reddit, "imgflip": imgflip, "cross": cross, "sources": status_rows,
    }
