"""Steam 스냅샷 → 리포트 dict (rules.md §4~§9)."""
from collections import Counter
from datetime import datetime

from . import series as series_mod
from .common import (State, delta, fmt_int, fmt_money, fmt_pct, fmt_signed, fmt_usd, load_snaps, pct,
                     round_no, streak_up, to_date, window_snap)

LIST_KO = {"topsellers": "Top Sellers", "popularnew": "New & Trending",
           "comingsoon": "Popular Upcoming", "newreleases": "New Releases"}
PRIMARY = ("popularnew", "topsellers")  # 급상승 판정에 쓰는 목록


def app_url(appid):
    return f"https://store.steampowered.com/app/{appid}/"


def build_records(cfg, date, snaps):
    today_snap = snaps[-1][1]
    prev_date, prev_snap = (snaps[-2] if len(snaps) >= 2 else (None, None))
    d7, s7, n7 = window_snap(snaps, date, 7)
    d30, s30, n30 = window_snap(snaps, date, 30)
    today = to_date(date)
    big = {p.lower() for p in cfg.get("big_publishers", [])}

    def ranks_of(snap):
        r = {}
        if not snap:
            return r
        for ln, rows in snap["lists"].items():
            for row in rows:
                r.setdefault(str(row["appid"]), {})[ln] = row["rank"]
        return r

    ranks_today, ranks_prev = ranks_of(today_snap), ranks_of(prev_snap)
    recs = {}
    for appid, a in today_snap["apps"].items():
        meta = a.get("meta") or {}
        spy = a.get("spy") or {}
        rel = meta.get("release_date")
        age = (today - to_date(rel)).days if rel else None
        coming = bool(meta.get("coming_soon")) or (appid in ranks_today and "comingsoon" in ranks_today[appid] and not rel)
        dev = (meta.get("developers") or [spy.get("developer")] or [None])[0]
        pub = (meta.get("publishers") or [spy.get("publisher")] or [None])[0]
        price_initial = meta.get("price_initial")
        if price_initial is None:
            price_initial = spy.get("initialprice")
        if meta.get("is_free") or (price_initial is None and a.get("price_final") == 0):
            price_initial = 0
        reviews = a.get("reviews_total")
        prev_app = (prev_snap or {}).get("apps", {}).get(appid, {}) if prev_snap else {}
        r7 = (s7 or {}).get("apps", {}).get(appid, {}).get("reviews_total") if s7 else None
        r30 = (s30 or {}).get("apps", {}).get(appid, {}).get("reviews_total") if s30 else None
        series = [reviews] + [s["apps"].get(appid, {}).get("reviews_total") for _, s in reversed(snaps[:-1])]

        excl = []
        if price_initial is not None and price_initial > cfg["max_price_usd"] * 100:
            excl.append(f"정가 {fmt_usd(price_initial)}")
        if pub and dev and pub != dev and pub.lower() in big:
            excl.append(f"대형 퍼블리셔 {pub}")
        if age is not None and age > cfg["max_age_years"] * 365:
            excl.append(f"출시 {age // 365}년")
        if reviews is not None and reviews >= cfg["max_reviews"]:
            excl.append(f"리뷰 {fmt_int(reviews)}")
        mult = cfg["review_multiplier"]["under_1y"] if (age is None or age <= 365) else cfg["review_multiplier"]["under_3y"]
        est_sales = reviews * mult if reviews is not None else None
        est_rev = est_sales * price_initial / 100 if (est_sales is not None and price_initial) else None
        discount = a.get("discount_pct") or spy.get("discount") or 0

        rec = {
            "appid": appid, "name": a.get("name") or meta.get("name") or appid, "url": app_url(appid),
            "dev": dev, "pub": pub, "self_pub": bool(dev and pub and dev == pub),
            "release_date": rel, "age": age, "coming_soon": coming,
            "new": bool(age is not None and age <= cfg["new_release_days"]),
            "price_initial": price_initial, "price_final": a.get("price_final"), "discount": discount,
            "has_demo": bool(meta.get("has_demo")), "genres": meta.get("genres") or [],
            "desc": _desc(meta.get("short_description")),
            # SteamSpy 태그는 신작에 비어 있는 일이 많아 appdetails 장르로 대신합니다.
            "tags": list((spy.get("tags") or {}).keys())[:5] or [g for g in (meta.get("genres") or []) if g != "Indie"][:3],
            "reviews": reviews, "pct_pos": a.get("review_pct"),
            "reviews_d1": delta(reviews, prev_app.get("reviews_total")),
            "reviews_d7": delta(reviews, r7), "n7": n7,
            "reviews_d30": delta(reviews, r30), "n30": n30,
            "growth7": pct(reviews, r7),
            "ccu": a.get("ccu_now"), "ccu_d1": pct(a.get("ccu_now"), prev_app.get("ccu_now")),
            "owners": spy.get("owners"), "avg_2weeks": spy.get("avg_2weeks"),
            "est_sales": est_sales, "est_rev": est_rev, "mult": mult,
            "ranks": ranks_today.get(appid, {}), "prev_ranks": ranks_prev.get(appid, {}),
            "included": not excl, "excl": excl, "streak": streak_up(series),
            "tracked_only": bool(a.get("tracked_only")),
        }
        rec["climb"] = max([(rec["prev_ranks"][ln] - rec["ranks"][ln], ln) for ln in PRIMARY
                            if ln in rec["ranks"] and ln in rec["prev_ranks"]] or [(None, None)])
        rec["verdict"] = verdict(rec, prev_snap is not None)
        recs[appid] = rec
    return recs, prev_date, (d7, n7), (d30, n30)


def verdict(r, has_prev):
    in_today = any(ln in r["ranks"] for ln in PRIMARY)
    in_prev = any(ln in r["prev_ranks"] for ln in PRIMARY)
    if not has_prev:
        return "회차 1 · 비교 없음"
    d1 = r["reviews_d1"]
    if r["reviews_d7"] and r["n7"] and d1 and d1 >= 50 and d1 > 10 * (r["reviews_d7"] / r["n7"]):
        return "리뷰 급증 의심 · 데이터 확인"
    if in_today and not in_prev:
        return "신규 진입" + (" · 할인 동반" if r["discount"] else "")
    if in_prev and not in_today:
        return "이탈 (규모 증가)" if (d1 or 0) > 0 else "이탈 (규모 정체)"
    if in_today and in_prev:
        c, _ = r["climb"]
        if r["streak"] >= 3 and not r["discount"]:
            return f"승격 통과 · {r['streak']}회차 오가닉"
        if r["streak"] >= 3:
            return f"꾸준한 상승 {r['streak']}회차 · 할인 중"
        if c and c > 0:
            return "상승" + (" · 할인 동반" if r["discount"] else "")
        if c and c < 0:
            return "하락"
        return "잔류"
    if r["tracked_only"]:
        return "목록 밖 추적" + (" · 규모 증가" if (d1 or 0) > 0 else "")
    return "—"


def line(r, with_rank=True):
    bits = []
    for ln in (("popularnew", "topsellers", "comingsoon") if with_rank else ()):
        if ln in r["ranks"]:
            p = r["prev_ranks"].get(ln)
            bits.append(f"{LIST_KO[ln]} {p}→{r['ranks'][ln]}위" if p and p != r["ranks"][ln] else f"{LIST_KO[ln]} {r['ranks'][ln]}위")
            break
    if r["reviews"] is not None:
        s = f"리뷰 {fmt_int(r['reviews'])}"
        if r["reviews_d1"] is not None:
            s += f"({fmt_signed(r['reviews_d1'])})"
        if r["reviews_d7"] is not None and r["n7"] > 1:  # 1일 창이면 1일 변화와 같아 생략
            s += f" · {r['n7']}일 {fmt_signed(r['reviews_d7'])}"
        bits.append(s)
    if r["ccu"] is not None:
        bits.append(f"동접 {fmt_int(r['ccu'])}" + (f"({fmt_pct(r['ccu_d1'])})" if r["ccu_d1"] is not None else ""))
    if r["price_initial"] is not None:  # 가격을 못 읽은 게임은 "—" 대신 조각을 생략
        bits.append(("무료" if r["price_initial"] == 0 else fmt_usd(r["price_initial"])) + (f" −{r['discount']}%" if r["discount"] else ""))
    return " · ".join(bits)


def badges(r):
    b = []
    if r["coming_soon"]:
        b.append("출시 예정")
    elif r["new"]:
        b.append("신작")
    if r["self_pub"]:
        b.append("셀프 퍼블리싱")
    if r["has_demo"]:
        b.append("데모")
    if r["discount"]:
        b.append(f"할인 {r['discount']}%")
    if not r["included"]:
        b.append("본문 제외")
    return b


DESC_LEN = 300


def _desc(s):
    """스토어 짧은 설명(영어 원문)을 300자로. 없으면 빈 문자열."""
    s = (s or "").strip()
    return s if len(s) <= DESC_LEN else s[: DESC_LEN - 1].rstrip() + "…"


def item(r, extra=None):
    d = {"name": r["name"], "url": r["url"], "line": extra or line(r), "badges": badges(r),
         "sub": " · ".join(x for x in (r["dev"], ", ".join(r["tags"][:3])) if x)}
    if r.get("desc"):
        d["desc"] = r["desc"]
    return d


def analyze(cfg, date, data_dir, reports_dir):
    snaps = load_snaps(data_dir, "steam", date)
    if not snaps or snaps[-1][0] != date:
        raise SystemExit(f"[steam] {date} 스냅샷이 없습니다.")
    recs, prev_date, (d7, n7), (d30, n30) = build_records(cfg, date, snaps)
    rn = round_no(data_dir, "steam", date)
    has_prev = prev_date is not None
    state = State(reports_dir / "steam" / "state.json")
    inc = [r for r in recs.values() if r["included"]]
    body = [r for r in inc if any(ln in r["ranks"] for ln in PRIMARY)]
    sections, headline, notes = [], [], []

    # ---- 01 급상승
    climbers = sorted([r for r in body if r["climb"][0] is not None and r["climb"][0] > 0], key=lambda r: -r["climb"][0])
    growth = sorted([r for r in body if r["growth7"] is not None and (r["reviews"] or 0) >= 30 and r["reviews_d7"] > 0], key=lambda r: -r["growth7"])
    volume = sorted([r for r in body if r["reviews_d7"]], key=lambda r: -r["reviews_d7"])
    if has_prev:
        blocks = [
            {"title": "① 순위 상승폭 (New & Trending · Top Sellers)",
             "items": [item(r, f"{LIST_KO[r['climb'][1]]} {r['prev_ranks'][r['climb'][1]]}→{r['ranks'][r['climb'][1]]}위 ▲{r['climb'][0]} · " + line(r)) for r in climbers[:3]]},
            {"title": f"② {n7}일 리뷰 증가율", "items": [item(r, f"{fmt_pct(r['growth7'])} ({fmt_signed(r['reviews_d7'])}) · " + line(r)) for r in growth[:3]]},
            {"title": f"③ 절대 규모 · {n7}일 리뷰 증가 수", "items": [item(r, f"{fmt_signed(r['reviews_d7'])} · 추정 판매 {fmt_int(r['est_sales'])} · " + line(r)) for r in volume[:3]]},
        ]
        basis = f"{prev_date} 대비 1일치. 리뷰 증가는 {d7}({n7}일 전) 대비. 본문 제외 게임은 06에만."
    else:
        top_new = [r for r in body if "popularnew" in r["ranks"]]
        top_new.sort(key=lambda r: r["ranks"]["popularnew"])
        top_sell = sorted([r for r in body if "topsellers" in r["ranks"]], key=lambda r: r["ranks"]["topsellers"])
        blocks = [
            {"title": "① New & Trending 상위 (본문 포함 기준)", "items": [item(r) for r in top_new[:3]]},
            {"title": "② Top Sellers 상위 (본문 포함 기준)", "items": [item(r) for r in top_sell[:3]]},
            {"title": "③ 동접 상위", "items": [item(r) for r in sorted(body, key=lambda r: -(r["ccu"] or 0))[:3]]},
        ]
        basis = "회차 1이라 비교 대상이 없습니다. 오늘 목록의 상위만 보여 주고, 급상승 판정은 회차 2부터 시작합니다."
    sections.append({"no": "01", "title": "급상승 Top 3 · 기준 3개", "basis": basis, "blocks": blocks})

    # ---- 02 꾸준한 상승
    steady = sorted([r for r in body if r["streak"] >= 2], key=lambda r: (-r["streak"], -(r["reviews_d7"] or 0)))
    if len(snaps) >= 3:
        blocks = [{"title": "연속 회차 리뷰 증가 (3회차 이상 승격 후보)",
                   "items": [item(r, f"{r['streak']}회차 연속 · {r['verdict']} · " + line(r)) for r in steady[:6]]}]
        basis = "직전 회차마다 리뷰가 늘어난 연속 횟수. 할인 없이 3회차를 채우면 승격 통과(오가닉)."
    else:
        blocks = []
        basis = f"스냅샷 {len(snaps)}회차. 연속 판정은 3회차부터 가능합니다."
    sections.append({"no": "02", "title": "꾸준한 상승 Top 3", "basis": basis, "blocks": blocks})

    # ---- 03 소재·장르
    focus = (climbers[:30] + growth[:30]) if has_prev else [r for r in body if "popularnew" in r["ranks"]][:40]
    focus = list({r["appid"]: r for r in focus}.values())
    cnt = Counter(t for r in focus for t in r["tags"])
    base = Counter(t for r in inc for t in r["tags"])
    rows = []
    for tag, n in cnt.most_common(12):
        share = n / max(len(focus), 1) * 100
        base_share = base[tag] / max(len(inc), 1) * 100
        ex = [r for r in focus if tag in r["tags"]][:3]
        n_streak, _ = state.bump(f"tag:{tag}", tag, date, prev_date)
        rows.append([tag, f"{n}개 ({share:.0f}%)", f"{base_share:.0f}%", f"{share / base_share:.1f}×" if base_share else "—",
                     " · ".join(f"[{r['name']}]({r['url']})" for r in ex), f"{n_streak}회차"])
    sections.append({"no": "03", "title": "소재 · 장르 뜨는 것", "basis": ("상승 게임" if has_prev else "New & Trending 상위") + " 묶음의 SteamSpy 태그 상위 5개를 세고, 전체 모집단 비율과 비교합니다. 배율이 1.5× 이상이면 그 소재가 지금 특히 뜨는 것입니다.",
                     "tables": [{"cols": ["태그", "상승 묶음", "전체 비율", "배율", "예시", "연속"], "rows": rows}]})

    # ---- 04 할인·이벤트
    listed = [r for r in body]
    disc = [r for r in listed if r["discount"]]
    organic_risers = [r for r in climbers if not r["discount"]] if has_prev else [r for r in listed if not r["discount"] and r["new"]][:5]
    disc_risers = [r for r in climbers if r["discount"]] if has_prev else disc[:5]
    demo = [r for r in inc if r["coming_soon"] and r["has_demo"]]
    coming_all = [r for r in inc if r["coming_soon"]]
    text = (f"본문 포함 {len(listed)}개 중 할인 중 {len(disc)}개({len(disc) / max(len(listed), 1) * 100:.0f}%). "
            + (f"상승 {len(climbers)}개 중 할인 없이 오른 것 {len(organic_risers)}개, 할인 동반 {len(disc_risers)}개. " if has_prev else "")
            + f"Popular Upcoming {len(coming_all)}개 중 데모 제공 {len(demo)}개.")
    sections.append({"no": "04", "title": "할인 · 이벤트와 상승의 관계", "basis": "광고비 지표가 없는 Steam에서는 할인이 상승의 외부 요인입니다. 할인 없이 오른 게임을 오가닉으로 봅니다.",
                     "text": text, "blocks": [
                         {"title": "오가닉 (할인 없음)", "items": [item(r) for r in organic_risers[:5]]},
                         {"title": "할인 동반", "items": [item(r) for r in disc_risers[:5]]},
                         {"title": "출시 예정 중 데모 제공", "items": [item(r) for r in sorted(demo, key=lambda r: r["ranks"].get("comingsoon", 999))[:5]]},
                     ]})

    # ---- 05 특이사항
    anomalies = [r for r in recs.values() if r["verdict"].startswith("리뷰 급증")]
    names = Counter(r["name"] for r in recs.values())
    dups = [n for n, c in names.items() if c > 1]
    exits_grow = [r for r in recs.values() if r["verdict"] == "이탈 (규모 증가)"]
    no_meta = [r for r in recs.values() if not r["release_date"] and not r["coming_soon"]]
    excl_cnt = Counter(e.split(" ")[0] for r in recs.values() for e in r["excl"])
    for r in anomalies[:3]:
        notes.append(f"[{r['name']}]({r['url']}) 하루 리뷰 {fmt_signed(r['reviews_d1'])} — 7일 평균의 10배 이상, 리뷰 폭탄이나 무료 배포 의심")
    for n in dups[:2]:
        notes.append(f"'{n}' 이름이 2개 appid로 집계 — 숫자 신뢰 주의")
    if exits_grow:
        notes.append("이탈(규모 증가) " + " · ".join(f"[{r['name']}]({r['url']}) {fmt_signed(r['reviews_d1'])}" for r in exits_grow[:3]) + " — 순위 밖에서 계속 성장")
    notes.append(f"본문 제외 {sum(1 for r in recs.values() if not r['included'])}개 (" + " · ".join(f"{k} {v}" for k, v in excl_cnt.most_common()) + ")")
    if no_meta:
        notes.append(f"출시일 메타 없음 {len(no_meta)}개 (appdetails 미응답, 다음 회차 재시도)")
    sections.append({"no": "05", "title": "특이사항 · 이상현상", "basis": "", "list": notes})

    # ---- 06 상세
    tables = []
    regions = (snaps[-1][1].get("params") or {}).get("regions") or []

    def region_cell(row):
        rg = row.get("regions")
        if not rg:
            return "—"
        return " · ".join(f"{k} {rg.get(k, '—')}" for k in (regions or sorted(rg)))

    for ln in ("popularnew", "topsellers", "comingsoon", "newreleases"):
        rows = []
        for row in snaps[-1][1]["lists"].get(ln, []):
            r = recs[str(row["appid"])]
            p = r["prev_ranks"].get(ln)
            rows.append([
                f"{row['rank']}" + (f" ({p}→)" if p and p != row["rank"] else ""),
                region_cell(row),
                f"[{r['name']}]({r['url']})" + ("" if r["included"] else " ⊘"),
                r["dev"] or "—", r["release_date"] or ("출시 예정" if r["coming_soon"] else "—"),
                ("무료" if r["price_initial"] == 0 else fmt_usd(r["price_initial"])) + (f" −{r['discount']}%" if r["discount"] else ""),
                f"{fmt_int(r['reviews'])}" + (f" ({fmt_signed(r['reviews_d1'])})" if r["reviews_d1"] is not None else ""),
                fmt_signed(r["reviews_d7"]) if r["reviews_d7"] is not None else "—",
                fmt_int(r["ccu"]), r["owners"] or "—", fmt_int(r["est_sales"]),
                ", ".join(r["tags"][:3]), r["verdict"] + (" · " + ", ".join(r["excl"]) if r["excl"] else ""),
            ])
        tables.append({"title": f"{LIST_KO[ln]} ({len(rows)}행)",
                       "cols": ["#", "지역 순위", "게임", "개발사", "출시", "가격", "리뷰 (1일)", f"{n7}일", "동접", "오너 구간", "추정 판매", "태그", "판정"],
                       "rows": rows})
    tracked = [r for r in recs.values() if r["tracked_only"]]
    if tracked:
        tables.append({"title": f"목록 밖 추적 ({len(tracked)}개, 최근 14일 안에 목록에 있었던 게임)",
                       "cols": ["게임", "리뷰 (1일)", f"{n7}일", "동접", "판정"],
                       "rows": [[f"[{r['name']}]({r['url']})", f"{fmt_int(r['reviews'])} ({fmt_signed(r['reviews_d1'])})", fmt_signed(r["reviews_d7"]), fmt_int(r["ccu"]), r["verdict"]] for r in tracked]})
    sections.append({"no": "06", "title": "상세", "basis": "필요할 때만 펼쳐 보십시오. ⊘ = 본문 제외. 추정 판매 = 리뷰 × 배수(1년 이내 30, 3년 이내 40), 비교용 추정치입니다.", "tables": tables})

    # ---- 오늘의 선정 · 큰 폭 변화
    # 회차 1(비교 없음)은 오늘 목록 상위 중심, 회차 2부터는 "오늘 오른 게임" 중심 (rules.md §9 오늘의 선정 게임).
    def score_round1(r):
        s = 0
        if r["growth7"]:
            s += min(r["growth7"], 200)
        if r["new"]:
            s += 30
        if not r["discount"]:
            s += 20
        if "popularnew" in r["ranks"]:
            s += max(0, 40 - r["ranks"]["popularnew"])
        s += min(r["reviews"] or 0, 500) / 25  # 리뷰가 거의 없는 게임이 순위만으로 뽑히지 않게
        return s

    def score(r):
        # 주 기준: 순위 상승폭(1계단 = 1점) + 리뷰 증가율(리뷰 30개 이상일 때, 100% = 30점) + 리뷰 증가 수(300개 = 30점).
        c = r["climb"][0] or 0
        s = max(c, 0)
        if r["growth7"] and (r["reviews"] or 0) >= 30:
            s += min(max(r["growth7"], 0), 100) * 0.3
        s += min(max(r["reviews_d7"] or 0, 0), 300) * 0.1
        # 보조 가산점(동점 처리용): 합계 9점 = 상승폭 10계단 미만.
        if r["new"]:
            s += 4
        if not r["discount"]:
            s += 3
        if r["has_demo"]:
            s += 2
        return s

    if has_prev:
        # 순위가 떨어진 게임, 순위·리뷰 변화가 모두 없는 게임은 후보에서 제외.
        cands = [r for r in body if (r["climb"][0] or 0) >= 0 and (r["climb"][0] or 0) + abs(r["reviews_d1"] or 0) > 0]
        pick = max(cands, key=score) if cands else (climbers[0] if climbers else None)
    else:
        pick = max(body, key=score_round1) if body else None
    if pick:
        n_sel, since = state.bump("pick", pick["name"], date, prev_date)
        pick_info = {"name": pick["name"], "url": pick["url"], "streak": n_sel, "since": since,
                     "links": [("Steam", pick["url"]), ("SteamDB", f"https://steamdb.info/app/{pick['appid']}/")],
                     "sub": " · ".join(x for x in (pick["dev"], ", ".join(pick["tags"][:3]), pick["release_date"]) if x),
                     "line": line(pick), "badges": badges(pick), "tags": pick["tags"][:5]}
        if pick.get("desc"):
            pick_info["desc"] = pick["desc"]
    else:
        pick_info = None
    if has_prev:
        for r in climbers[:2]:
            headline.append(f"[{r['name']}]({r['url']}) {LIST_KO[r['climb'][1]]} {r['prev_ranks'][r['climb'][1]]}→{r['ranks'][r['climb'][1]]}위 ▲{r['climb'][0]}"
                            + (f" · {n7}일 리뷰 {fmt_signed(r['reviews_d7'])}" if r["reviews_d7"] is not None else " · " + line(r, with_rank=False))
                            + (" · 할인 동반" if r["discount"] else " · 할인 없음"))
        for r in growth[:1]:
            if r not in climbers[:2]:
                headline.append(f"[{r['name']}]({r['url']}) {n7}일 리뷰 {fmt_pct(r['growth7'])} ({fmt_signed(r['reviews_d7'])}) · " + line(r))
    else:
        for b in sections[0]["blocks"]:
            if b["items"]:
                it = b["items"][0]
                headline.append(f"{b['title'][2:].strip()}: [{it['name']}]({it['url']}) · {it['line']}")

    n_new = sum(1 for r in body if r["new"])
    status = [("회차", f"{rn}회차"), ("비교 대상", f"{prev_date} · 1일치" if prev_date else "없음 (첫 회차)"),
              ("리뷰 창", f"{d7} 대비 {n7}일" if d7 else "—"), ("모집단", f"{len(recs)}개 · 본문 {len(body)}개"),
              ("신작", f"{n_new}/{len(body)}"), ("수집", snaps[-1][1]["collected_at"][:16].replace("T", " ") + " UTC")]
    n_lists_ok = sum(1 for rows in snaps[-1][1]["lists"].values() if rows)
    n_fail = len(snaps[-1][1].get("failed") or [])
    collect_line = (f"수집 목록 {n_lists_ok}/{len(snaps[-1][1]['lists'])} 정상 · 모집단 {len(recs)} · 본문 포함 {len(body)} · 신작 {n_new} · 제외 {len(recs) - len(inc)}"
                    + (f" · API 실패 {n_fail}건" if n_fail else ""))
    state.save()
    # 최근 7일 시계열(표지 스파크라인 · 범프 차트 · 가장 크게 오른/내린 게임). 렌더러가 rep["series"] 로 읽습니다.
    pick_list = next((ln for ln in ("popularnew", "topsellers", "comingsoon") if pick and ln in pick["ranks"]), "topsellers") if pick else None
    series_blk = series_mod.report_block(data_dir, "steam", date, "topsellers", pick_id=pick["appid"] if pick else None, pick_list=pick_list)
    region_line = (f"글로벌 합성({len(regions)}개 지역 평균 순위: {'·'.join(r.upper() for r in regions)}) · 가격 USD"
                   if len(regions) > 1 else "미국 스토어")
    return {"platform": "steam", "platform_ko": "Steam 인디", "date": date, "round": rn, "prev_date": prev_date,
            "status": status, "pick": pick_info, "headline": headline[:3], "notes": notes[:3],
            "sections": sections, "collect_line": collect_line, "series": series_blk,
            "basis_line": f"Steam 검색 · Indie 태그 · {region_line} · 목록 4개(Top Sellers 200 · New & Trending · Popular Upcoming 100 · New Releases 100) · 본문 포함 = 정가 ${cfg['max_price_usd']} 이하 · 3년 이내 · 리뷰 {fmt_int(cfg['max_reviews'])} 미만 · 신작 = 1년 이내"}
