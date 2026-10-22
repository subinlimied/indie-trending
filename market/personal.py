"""개인 리포트 분석: 공용 리포트의 레코드를 profile.json 으로 다시 걸러 "내 범위" Top 3 를 뽑습니다.

입력은 report.py 가 저장한 reports/<platform>/<date>.json (공용 리포트 dict) 과
analyze_steam.build_records / analyze_itch.build_records 가 스냅샷에서 만든 레코드입니다.
분석을 다시 하지 않고, 공용 리포트가 이미 계산한 순위 변화·리뷰 증가를 그대로 씁니다.
"""
import itertools
from collections import Counter, defaultdict

from . import analyze_itch, analyze_steam
from .common import fmt_int, fmt_pct, fmt_signed, fmt_usd, to_date
from .render import LINK

# Steam 검색 결과의 data-ds-tagids (상위 7개) → 태그 이름. SteamSpy 태그가 비어 있는 신작에서 보조로 씁니다.
STEAM_TAG_IDS = {3871: "2D", 4191: "3D", 3859: "Multiplayer", 1685: "Co-op", 3843: "Online Co-Op", 3841: "Local Co-Op",
                 128: "Massively Multiplayer", 4182: "Singleplayer", 9551: "Dating Sim", 31275: "Otome", 4947: "Romance",
                 3799: "Visual Novel", 1775: "PvP", 3964: "Pixel Graphics"}
MP_TAGS = {"multiplayer", "mmo", "mmorpg", "massively multiplayer", "co-op", "online co-op", "local co-op",
           "local multiplayer", "pvp", "co-op campaign", "online pvp"}
SP_TAGS = {"singleplayer", "single-player", "single player"}
# itch 페이지의 "Average session" → 시간
ITCH_SESSION_HOURS = {"A few seconds": 0.02, "A few minutes": 0.1, "About a half-hour": 0.5, "About an hour": 1.0,
                      "A few hours": 3.0, "Days or more": 48.0}
GENERIC_TAGS = {"indie", "singleplayer", "2d", "3d", "casual", "early access", "free to play"}


# ---------- 레코드 정규화 (Steam·itch 를 같은 꼴로) ----------

def _dim(tags):
    low = [t.lower() for t in tags]
    if any(t == "2d" or t.startswith("2d ") for t in low):
        return "2D"
    if any(t == "3d" or t.startswith("3d ") for t in low):
        return "3D"
    return None


def _price_usd(text):
    if not text:
        return None
    try:
        return float(text.replace("$", "").replace(",", ""))
    except ValueError:
        return None


def norm_steam(r, app):
    """analyze_steam 레코드 + 스냅샷 앱 → 공통 게임 dict."""
    spy = app.get("spy") or {}
    tags = list((spy.get("tags") or {}).keys())
    for tid in app.get("tagids") or []:
        nm = STEAM_TAG_IDS.get(tid)
        if nm and nm not in tags:
            tags.append(nm)
    mins = spy.get("average_forever") or spy.get("avg_forever") or spy.get("avg_2weeks") or 0
    return {
        "platform": "steam", "id": r["appid"], "name": r["name"], "url": r["url"],
        "tags": tags, "show_tags": r["tags"][:3], "dim": _dim(tags), "engine": None,
        "price_usd": (r["price_initial"] / 100) if r["price_initial"] is not None else None,
        "playtime_h": round(mins / 60, 1) if mins else None,
        "reviews": r["reviews"], "d1": r["reviews_d1"], "d7": r["reviews_d7"], "n7": r["n7"], "growth7": r["growth7"],
        "climb": r["climb"], "ranks": r["ranks"], "prev_ranks": r["prev_ranks"], "list_ko": analyze_steam.LIST_KO,
        "new": r["new"], "age": r["age"], "coming_soon": r["coming_soon"], "has_demo": r["has_demo"],
        "self_pub": r["self_pub"], "sale": bool(r["discount"]), "status": None,
        "public_excl": r["excl"], "verdict": r["verdict"], "streak": r["streak"],
        "in_body": r["included"] and any(ln in r["ranks"] for ln in analyze_steam.PRIMARY),
        "line": analyze_steam.line(r), "line_norank": analyze_steam.line(r, with_rank=False),
        "badges": analyze_steam.badges(r), "thumb": None, "thumb_bg": None,
        "sub": " · ".join(x for x in (r["dev"], ", ".join(r["tags"][:3])) if x),
    }


def norm_itch(r, game):
    page = game.get("page") or {}
    session = page.get("session")
    engines = page.get("made_with") or []
    engine = next((e for e in engines if e in analyze_itch.ENGINES), None)
    return {
        "platform": "itch", "id": r["id"], "name": r["title"], "url": r["url"],
        "tags": list(r["tags"]) + ([r["genre"]] if r["genre"] else []), "show_tags": r["tags"][:3], "dim": _dim(r["tags"]), "engine": engine,
        "price_usd": 0.0 if (r["free"] or r["nyop"]) else _price_usd(r["price"]),
        "playtime_h": ITCH_SESSION_HOURS.get(session) if session else None, "session": session,
        "reviews": r["rating"], "d1": r["rating_d1"], "d7": r["rating_d7"], "n7": r["n7"], "growth7": r["growth7"],
        "climb": r["climb"], "ranks": r["ranks"], "prev_ranks": r["prev_ranks"], "list_ko": analyze_itch.LIST_KO,
        "new": r["new"], "age": r["age"], "coming_soon": False, "has_demo": False,
        "self_pub": True, "sale": r["sale"], "status": r["status"],
        "public_excl": r["excl"], "verdict": r["verdict"], "streak": r["streak"],
        "in_body": r["included"] and any(ln in r["ranks"] for ln in analyze_itch.PRIMARY),
        "line": analyze_itch.line(r), "line_norank": analyze_itch.line(r, with_rank=False),
        "badges": analyze_itch.badges(r), "thumb": r.get("thumb"), "thumb_bg": r.get("thumb_bg"),
        "sub": " · ".join(x for x in (r["author"], r["genre"], ", ".join(r["tags"][:3])) if x),
        "price_text": analyze_itch.price_text(r),
    }


# ---------- profile 판정 ----------

def check(g, prof):
    """내 범위 조건을 못 넘은 이유 목록. 비어 있으면 내 범위."""
    out = list(g["public_excl"])  # 공용 본문 제외 조건(정가 $30·대형 퍼블리셔·3년·리뷰 5만)은 그대로 상속
    low = {t.lower() for t in g["tags"]}
    dims = prof.get("dimensions") or []
    if dims and g["dim"] and g["dim"] not in dims:
        out.append(f"{g['dim']} 제외")
    eng = prof.get("engines") or []
    if eng and g["engine"] and g["engine"] not in eng:
        out.append(f"엔진 {g['engine']}")
    hit = [t for t in (prof.get("exclude_tags") or []) if t.lower() in low]
    if hit:
        out.append("태그 " + ", ".join(hit[:2]))
    mx = prof.get("max_price_usd")
    if mx is not None and g["price_usd"] is not None and g["price_usd"] > mx:
        out.append(f"정가 ${g['price_usd']:,.2f}")
    mh = prof.get("max_playtime_hours")
    if mh is not None and g["playtime_h"] is not None and g["playtime_h"] > mh:
        out.append(f"플레이 {g['playtime_h']:g}시간")
    if prof.get("exclude_multiplayer") and (low & MP_TAGS) and not (low & SP_TAGS):
        out.append("Multiplayer")
    return out


def score(g, prof, has_prev):
    """공용 선정 점수식과 같은 뼈대(순위 상승폭 + 증가율 + 증가 수 + 보조 가산점)에 선호 태그 가산점만 더합니다."""
    min_sig = prof.get("min_reviews_for_signal") or 0
    s = 0.0
    if has_prev:
        c = g["climb"][0] or 0
        s += max(c, 0)
        if g["growth7"] and (g["reviews"] or 0) >= min_sig:
            s += min(max(g["growth7"], 0), 100) * 0.3
        if g["platform"] == "steam":
            s += min(max(g["d7"] or 0, 0), 300) * 0.1
        else:
            s += min(max(g["d7"] or 0, 0), 50) * 0.5
        if g["new"]:
            s += 4
        if not g["sale"]:
            s += 3
        if g["has_demo"] or g["engine"]:
            s += 2
    else:
        if g["growth7"]:
            s += min(g["growth7"], 200)
        if g["new"]:
            s += 30
        if not g["sale"]:
            s += 20 if g["platform"] == "steam" else 10
        top = "popularnew" if g["platform"] == "steam" else "new-and-popular"
        if top in g["ranks"]:
            s += max(0, 40 - g["ranks"][top])
        s += min(g["reviews"] or 0, 500) / 25 if g["platform"] == "steam" else min(g["reviews"] or 0, 100) / 5
    low = {t.lower() for t in g["tags"]}
    s += 2 * min(3, sum(1 for t in (prof.get("prefer_tags") or []) if t.lower() in low))
    return s


def key_line(g):
    """항목 첫 조각(큰 숫자) + 공용 line. render.key_metric 이 읽는 형식을 지킵니다."""
    c, ln = g["climb"]
    unit = "리뷰" if g["platform"] == "steam" else "평점 수"
    if c and c > 0:  # 순위 조각이 큰 숫자로 앞에 나가므로 뒤 line 에서는 뺍니다
        return f"{g['list_ko'][ln]} {g['prev_ranks'][ln]}→{g['ranks'][ln]}위 ▲{c} · " + g["line_norank"]
    if g["growth7"] and g["growth7"] > 0 and (g["d7"] or 0) > 0:
        return f"{fmt_pct(g['growth7'])} ({fmt_signed(g['d7'])}) · " + g["line"]
    if (g["d7"] or 0) > 0:
        return f"{fmt_signed(g['d7'])} · " + g["line"]
    return g["line"]


def fact_bits(g):
    """제작 관점 메모용 사실 조각: 차원 · 태그 · 가격 · 플레이 시간 · 데모 · 퍼블리싱 · 엔진."""
    bits = []
    if g["dim"]:
        bits.append(g["dim"])
    tags = [t for t in g["show_tags"] if t.lower() not in GENERIC_TAGS][:3] or g["show_tags"][:2]
    if tags:
        bits.append(" · ".join(tags))
    if g["platform"] == "steam":
        bits.append("무료" if g["price_usd"] == 0 else (f"${g['price_usd']:,.2f}" if g["price_usd"] is not None else "가격 미상"))
        bits.append(f"평균 {g['playtime_h']:g}시간" if g["playtime_h"] else "플레이 시간 미상")
        if g["has_demo"]:
            bits.append("데모 있음")
        bits.append("셀프 퍼블리싱" if g["self_pub"] else "퍼블리셔 있음")
    else:
        bits.append(g.get("price_text") or "무료")
        bits.append(f"세션 {g['session']}" if g.get("session") else "세션 길이 미상")
        if g["engine"]:
            bits.append(g["engine"])
        if g["status"] and g["status"] != "Released":
            bits.append(g["status"])
    if g["new"]:
        bits.append("신작")
    return bits


def item(g, prof, has_prev, pub_pick, pub_headline):
    same = None
    if pub_pick and g["name"] == pub_pick:
        same = "공용 선정과 동일"
    elif g["name"] in pub_headline:
        same = "공용 큰 폭 변화와 동일"
    return {"platform": g["platform"], "id": g["id"], "name": g["name"], "url": g["url"], "line": key_line(g),
            "badges": [b for b in g["badges"] if b != "본문 제외"][:4], "sub": g["sub"], "thumb": g["thumb"], "thumb_bg": g["thumb_bg"],
            "score": round(score(g, prof, has_prev), 1), "same": same, "facts": fact_bits(g),
            "tags": [t for t in g["tags"] if t.lower() not in GENERIC_TAGS][:5], "reviews": g["reviews"], "d1": g["d1"], "age": g["age"], "new": g["new"]}


def _pub_names(rep):
    pick = (rep.get("pick") or {}).get("name")
    heads = [m[0] for h in (rep.get("headline") or []) for m in LINK.findall(h)]
    top3 = [it["name"] for it in (rep["sections"][0]["blocks"][0]["items"] if rep.get("sections") else [])][:3]
    return pick, heads, top3


def analyze_platform(platform, rep, games, prof):
    """한 플랫폼의 내 범위 Top 3 와 밀려난 공용 게임."""
    has_prev = rep.get("prev_date") is not None
    pub_pick, pub_heads, pub_top3 = _pub_names(rep)
    by_name = {g["name"]: g for g in games}
    for g in games:
        g["fail"] = check(g, prof)
    body = [g for g in games if g["in_body"]]
    mine = [g for g in body if not g["fail"]]
    if has_prev:
        cands = [g for g in mine if (g["climb"][0] or 0) >= 0 and (g["climb"][0] or 0) + abs(g["d1"] or 0) > 0]
        if not cands:
            cands = [g for g in mine if (g["climb"][0] or 0) > 0]
    else:
        cands = mine
    ranked = sorted(cands, key=lambda g: -score(g, prof, has_prev))
    top = [item(g, prof, has_prev, pub_pick, pub_heads) for g in ranked[:3]]

    # 밀려난 공용 게임: 선정 게임·큰 폭 변화 중 내 범위 조건을 못 넘은 것
    pushed = []
    for nm in dict.fromkeys(([pub_pick] if pub_pick else []) + pub_heads):
        g = by_name.get(nm)
        if g and g["fail"]:
            pushed.append({"name": nm, "url": g["url"], "reasons": g["fail"][:3], "role": "선정" if nm == pub_pick else "큰 폭 변화"})

    # 1위가 공용과 다르면 한 줄 이유
    why = ""
    if top and top[0]["same"] != "공용 선정과 동일":
        g1 = ranked[0]
        pg = by_name.get(pub_pick) if pub_pick else None
        head = f"내 범위 1위 {g1['name']}: " + key_line(g1).split(" · ")[0]
        if pg is not None and pg["fail"]:
            why = f"공용 선정 {pub_pick} 은 {', '.join(pg['fail'][:2])} 로 내 범위 밖 → " + head
        elif pg is not None:
            why = f"공용 선정 {pub_pick} 보다 내 범위 점수가 높음 ({score(g1, prof, has_prev):.0f} vs {score(pg, prof, has_prev):.0f}) → " + head
        elif pub_pick:
            why = f"공용 선정 {pub_pick} 은 오늘 레코드에 없음 → " + head
        else:
            why = "공용 선정 게임 없음 → " + head
    elif top:
        why = ""  # 1위가 공용 선정과 같으면 항목의 '공용 선정과 동일' 표시로 충분

    same_as_public = bool(top) and top[0]["same"] == "공용 선정과 동일" and [t["name"] for t in top] == pub_top3
    fail_cnt = Counter(f.split(" ")[0] for g in body for f in g["fail"] if f not in g["public_excl"])
    pool = [{"platform": platform, "id": g["id"], "name": g["name"], "url": g["url"], "reviews": g["reviews"], "d1": g["d1"],
             "age": g["age"], "tags": [t for t in g["tags"] if t.lower() not in GENERIC_TAGS][:4]}
            for g in mine if g["age"] is not None and 0 <= g["age"] <= 90]
    return {"platform": platform, "platform_ko": rep["platform_ko"], "round": rep["round"], "has_prev": has_prev,
            "top": top, "pushed": pushed, "why": why, "same_as_public": same_as_public,
            "public": {"pick": pub_pick, "headline": pub_heads, "top3": pub_top3},
            "counts": {"body": len(body), "mine": len(mine), "cands": len(cands)},
            "fail_line": " · ".join(f"{k} {v}" for k, v in fail_cnt.most_common(5)),
            "pool": pool, "thumbs": {g["url"]: {"src": g["thumb"], "bg": g["thumb_bg"]} for g in ranked[:3] if g["thumb"]}}


def watchlist(prof, games_by_platform):
    """profile.watchlist 의 게임이 오늘 레코드에 있으면 변화 한 줄, 없으면 '오늘 목록에 없음'."""
    out = []
    for platform in ("steam", "itch"):
        ids = [str(x) for x in (prof.get("watchlist") or {}).get(platform) or []]
        by_id = {str(g["id"]): g for g in games_by_platform.get(platform, [])}
        for i in ids:
            g = by_id.get(i)
            if g:
                out.append({"platform": platform, "id": i, "name": g["name"], "url": g["url"], "line": g["verdict"] + " · " + g["line"],
                            "in_range": not g["fail"], "reasons": g["fail"][:2]})
            else:
                out.append({"platform": platform, "id": i, "name": None, "url": None, "line": "오늘 스냅샷에 없음", "in_range": None, "reasons": []})
    return out


def memo(plats):
    """오늘 내 범위 1위(Steam 우선, 없으면 itch)의 사실 조각 한 줄."""
    for p in ("steam", "itch"):
        pl = plats.get(p)
        if pl and pl["top"]:
            t = pl["top"][0]
            return {"name": t["name"], "url": t["url"], "platform": p, "text": " · ".join(t["facts"])}
    return None


# ---------- 주간 (월요일) ----------

def weekly(date, daily_results):
    """지난 7일 개인 리포트(오늘 포함) → 자주 오른 태그 조합 Top 3 · 리뷰가 가장 빨리 쌓인 신작 3개."""
    days = sorted({r["date"] for r in daily_results})
    combos = Counter()
    for r in daily_results:
        for pl in r.get("platforms", {}).values():
            for t in pl.get("top", []):
                tags = sorted(set(t.get("tags") or []))[:5]
                for a, b in itertools.combinations(tags, 2):
                    combos[(a, b)] += 1
    top_combos = [{"tags": list(k), "n": n} for k, n in combos.most_common(3)]

    seen = defaultdict(list)
    for r in daily_results:
        for pl in r.get("platforms", {}).values():
            for g in pl.get("pool", []):
                seen[(g["platform"], str(g["id"]))].append((r["date"], g))
    fast = []
    for (platform, gid), obs in seen.items():
        obs.sort()
        first, last = obs[0], obs[-1]
        span = (to_date(last[0]) - to_date(first[0])).days
        r0, r1 = first[1].get("reviews"), last[1].get("reviews")
        if span >= 1 and r0 is not None and r1 is not None:
            rate, basis = (r1 - r0) / span, f"{span + 1}일 관측"
        else:
            d1 = last[1].get("d1")
            if d1 is None:
                continue
            rate, basis = float(d1), "1일 관측"
        if rate <= 0:
            continue
        g = last[1]
        fast.append({"platform": platform, "name": g["name"], "url": g["url"], "rate": round(rate, 1), "reviews": r1,
                     "age": g.get("age"), "basis": basis, "tags": g.get("tags") or []})
    fast.sort(key=lambda x: -x["rate"])
    return {"days": len(days), "from": days[0] if days else date, "to": days[-1] if days else date,
            "combos": top_combos, "fast": fast[:3]}
