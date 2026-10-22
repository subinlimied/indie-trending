"""itch.io 스냅샷 → 리포트 dict."""
from collections import Counter

from .common import (State, delta, fmt_int, fmt_pct, fmt_signed, load_snaps, pct, round_no, streak_up,
                     to_date, window_snap)

LIST_KO = {"new-and-popular": "New & Popular", "top-sellers": "Top Sellers", "popular": "Popular",
           "top-rated": "Top Rated", "newest": "Newest"}
PRIMARY = ("new-and-popular", "top-sellers", "popular")


def build_records(cfg, date, snaps):
    today_snap = snaps[-1][1]
    prev_date, prev_snap = (snaps[-2] if len(snaps) >= 2 else (None, None))
    d7, s7, n7 = window_snap(snaps, date, 7)
    today = to_date(date)

    def ranks_of(snap):
        r = {}
        if not snap:
            return r
        for ln, rows in snap["lists"].items():
            for row in rows:
                r.setdefault(str(row["id"]), {})[ln] = row["rank"]
        return r

    ranks_today, ranks_prev = ranks_of(today_snap), ranks_of(prev_snap)
    excl_tags = {t.lower() for t in cfg.get("exclude_tags", [])}
    recs = {}
    for gid, g in today_snap["games"].items():
        p = g.get("page") or {}
        prev_g = (prev_snap or {}).get("games", {}).get(gid, {}) if prev_snap else {}
        pp = prev_g.get("page") or {}
        p7 = ((s7 or {}).get("games", {}).get(gid, {}).get("page") or {}) if s7 else {}
        rc = p.get("rating_count")
        series = [rc] + [((s["games"].get(gid) or {}).get("page") or {}).get("rating_count") for _, s in reversed(snaps[:-1])]
        pub = p.get("published")
        # 공개일이 없으면(개발 중 게임에 흔함) 나이를 모르는 것으로 두고 신작 집계에서 뺍니다.
        age = (today - to_date(pub)).days if pub else None
        tags = p.get("tags") or []
        excl = []
        if any(t.lower() in excl_tags for t in tags):
            excl.append("제외 태그")
        price = g.get("price")
        free = _is_zero_price(price) and not p.get("nyop")
        rec = {
            "id": gid, "title": g.get("title") or gid, "url": g.get("url"), "author": g.get("author"),
            "thumb": g.get("thumb"), "thumb_bg": g.get("thumb_bg"),
            "genre": (p.get("genre") or [g.get("genre")] or [None])[0], "tags": tags[:6],
            "made_with": [m for m in (p.get("made_with") or []) if m in ENGINES][:2],
            "price": price, "free": free, "nyop": bool(p.get("nyop")), "sale": bool(g.get("sale")),
            "platforms": g.get("platforms") or [], "status": p.get("status"),
            "published": pub, "age": age,
            "new": age is not None and age <= 365,
            "rating": rc, "rating_value": p.get("rating_value"),
            "rating_d1": delta(rc, pp.get("rating_count")), "rating_d7": delta(rc, p7.get("rating_count")), "n7": n7,
            "growth7": pct(rc, p7.get("rating_count")),
            "comments": p.get("comments"), "comments_d1": delta(p.get("comments"), pp.get("comments")),
            "devlog_latest": p.get("devlog_latest"), "steam_url": p.get("steam_url"), "jam": p.get("jam") or [],
            "ranks": ranks_today.get(gid, {}), "prev_ranks": ranks_prev.get(gid, {}),
            "included": not excl, "excl": excl, "streak": streak_up(series),
            "page_ok": bool(p) and "error" not in p,
        }
        rec["climb"] = max([(rec["prev_ranks"][ln] - rec["ranks"][ln], ln) for ln in PRIMARY
                            if ln in rec["ranks"] and ln in rec["prev_ranks"]] or [(None, None)])
        rec["verdict"] = verdict(rec, prev_snap is not None)
        recs[gid] = rec
    return recs, prev_date, (d7, n7)


def _is_zero_price(price):
    """목록 셀의 가격 텍스트가 없거나 '$0', '$0.00' 이면 무료."""
    if not price:
        return True
    try:
        return float(price.replace("$", "").replace(",", "")) == 0
    except ValueError:
        return False


ENGINES = {"Unity", "Godot", "GameMaker", "Unreal Engine", "Construct", "RPG Maker", "Ren'Py", "Twine", "PICO-8",
           "Love2D", "Phaser", "Bitsy", "Defold", "MonoGame", "libGDX", "Pygame", "Scratch", "Clickteam Fusion", "Stencyl", "GDevelop"}


def verdict(r, has_prev):
    in_today = any(ln in r["ranks"] for ln in PRIMARY)
    in_prev = any(ln in r["prev_ranks"] for ln in PRIMARY)
    if not has_prev:
        return "회차 1 · 비교 없음"
    if in_today and not in_prev:
        return "신규 진입" + (" · 세일" if r["sale"] else "")
    if in_prev and not in_today:
        return "이탈 (규모 증가)" if (r["rating_d1"] or 0) > 0 else "이탈 (규모 정체)"
    if in_today and in_prev:
        c, _ = r["climb"]
        if r["streak"] >= 3 and not r["sale"]:
            return f"승격 통과 · {r['streak']}회차 오가닉"
        if c and c > 0:
            return "상승" + (" · 세일" if r["sale"] else "")
        if c and c < 0:
            return "하락"
        return "잔류"
    return "—"


def price_text(r):
    if r["nyop"]:
        return "NYOP"
    if r["free"]:
        return "무료"
    return r["price"] or "유료"


def line(r, with_rank=True):
    bits = []
    for ln in (PRIMARY if with_rank else ()):
        if ln in r["ranks"]:
            p = r["prev_ranks"].get(ln)
            bits.append(f"{LIST_KO[ln]} {p}→{r['ranks'][ln]}위" if p and p != r["ranks"][ln] else f"{LIST_KO[ln]} {r['ranks'][ln]}위")
            break
    if r["rating"] is not None:
        s = f"평점 {fmt_int(r['rating'])}개"
        if r["rating_d1"] is not None:
            s += f"({fmt_signed(r['rating_d1'])})"
        if r["rating_d7"] is not None and r["n7"] > 1:  # 1일 창이면 1일 변화와 같아 생략
            s += f" · {r['n7']}일 {fmt_signed(r['rating_d7'])}"
        if r["rating_value"]:
            s += f" · {r['rating_value']}★"
        bits.append(s)
    if r["comments"] is not None:
        bits.append(f"댓글 {r['comments']}" + (f"({fmt_signed(r['comments_d1'])})" if r["comments_d1"] else ""))
    bits.append(price_text(r) + (" 세일" if r["sale"] else ""))
    return " · ".join(bits)


def badges(r):
    b = []
    if r["status"] and r["status"] != "Released":
        b.append(r["status"])
    if r["new"]:
        b.append("신작")
    if r["made_with"]:
        b.append(r["made_with"][0])
    if r["jam"] and r["new"]:
        b.append("게임잼")  # 오래된 상용 게임이 뒤늦게 잼에 낸 경우는 제외
    if not r["published"]:
        b.append("공개일 미상")
    if r["steam_url"]:
        b.append("Steam 있음")
    if "web" in r["platforms"]:
        b.append("웹")
    return b


def item(r, extra=None):
    return {"name": r["title"], "url": r["url"], "line": extra or line(r), "badges": badges(r),
            "thumb": r.get("thumb"), "thumb_bg": r.get("thumb_bg"),
            "sub": " · ".join(x for x in (r["author"], r["genre"], ", ".join(r["tags"][:3])) if x)}


def analyze(cfg, date, data_dir, reports_dir):
    snaps = load_snaps(data_dir, "itch", date)
    if not snaps or snaps[-1][0] != date:
        raise SystemExit(f"[itch] {date} 스냅샷이 없습니다.")
    recs, prev_date, (d7, n7) = build_records(cfg, date, snaps)
    rn = round_no(data_dir, "itch", date)
    has_prev = prev_date is not None
    state = State(reports_dir / "itch" / "state.json")
    inc = [r for r in recs.values() if r["included"]]
    body = [r for r in inc if any(ln in r["ranks"] for ln in PRIMARY)]
    sections, headline, notes = [], [], []

    climbers = sorted([r for r in body if r["climb"][0] is not None and r["climb"][0] > 0], key=lambda r: -r["climb"][0])
    growth = sorted([r for r in body if r["growth7"] is not None and (r["rating"] or 0) >= 10 and r["rating_d7"] > 0], key=lambda r: -r["growth7"])
    volume = sorted([r for r in body if r["rating_d7"]], key=lambda r: -r["rating_d7"])
    if has_prev:
        blocks = [
            {"title": "① 순위 상승폭 (New & Popular · Top Sellers · Popular)",
             "items": [item(r, f"{LIST_KO[r['climb'][1]]} {r['prev_ranks'][r['climb'][1]]}→{r['ranks'][r['climb'][1]]}위 ▲{r['climb'][0]} · " + line(r)) for r in climbers[:3]]},
            {"title": f"② {n7}일 평점 수 증가율", "items": [item(r, f"{fmt_pct(r['growth7'])} ({fmt_signed(r['rating_d7'])}) · " + line(r)) for r in growth[:3]]},
            {"title": f"③ 절대 규모 · {n7}일 평점 증가 수", "items": [item(r, f"{fmt_signed(r['rating_d7'])} · " + line(r)) for r in volume[:3]]},
        ]
        basis = f"{prev_date} 대비 1일치. 평점 수는 itch에서 유일하게 누적되는 공개 지표라 다운로드 대리값으로 씁니다."
    else:
        nap = sorted([r for r in body if "new-and-popular" in r["ranks"]], key=lambda r: r["ranks"]["new-and-popular"])
        ts = sorted([r for r in body if "top-sellers" in r["ranks"]], key=lambda r: r["ranks"]["top-sellers"])
        blocks = [
            {"title": "① New & Popular 상위", "items": [item(r) for r in nap[:3]]},
            {"title": "② Top Sellers 상위", "items": [item(r) for r in ts[:3]]},
            {"title": "③ 평점 수 상위 (신작)", "items": [item(r) for r in sorted([r for r in body if r["new"]], key=lambda r: -(r["rating"] or 0))[:3]]},
        ]
        basis = "회차 1이라 비교 대상이 없습니다. 오늘 목록 상위만 보여 주고, 급상승 판정은 회차 2부터 시작합니다."
    sections.append({"no": "01", "title": "급상승 Top 3 · 기준 3개", "basis": basis, "blocks": blocks})

    steady = sorted([r for r in body if r["streak"] >= 2], key=lambda r: (-r["streak"], -(r["rating_d7"] or 0)))
    if len(snaps) >= 3:
        blocks = [{"title": "연속 회차 평점 증가", "items": [item(r, f"{r['streak']}회차 연속 · {r['verdict']} · " + line(r)) for r in steady[:6]]}]
        basis = "직전 회차마다 평점 수가 늘어난 연속 횟수. 세일 없이 3회차면 승격 통과."
    else:
        blocks, basis = [], f"스냅샷 {len(snaps)}회차. 연속 판정은 3회차부터 가능합니다."
    sections.append({"no": "02", "title": "꾸준한 상승 Top 3", "basis": basis, "blocks": blocks})

    # 03 태그·장르·엔진
    focus = list({r["id"]: r for r in ((climbers[:30] + growth[:30]) if has_prev else [r for r in body if "new-and-popular" in r["ranks"]][:60])}.values())
    tables = []
    for title, key in (("태그", "tags"), ("장르", "genre"), ("엔진", "made_with")):
        get = (lambda r: r[key]) if key != "genre" else (lambda r: [r["genre"]] if r["genre"] else [])
        cnt = Counter(t for r in focus for t in get(r))
        base = Counter(t for r in inc for t in get(r))
        rows = []
        for t, n in cnt.most_common(8 if key == "tags" else 5):
            share = n / max(len(focus), 1) * 100
            bs = base[t] / max(len(inc), 1) * 100
            ex = [r for r in focus if t in get(r)][:3]
            st, _ = state.bump(f"{key}:{t}", t, date, prev_date)
            rows.append([t, f"{n}개 ({share:.0f}%)", f"{bs:.0f}%", f"{share / bs:.1f}×" if bs else "—",
                         " · ".join(f"[{r['title']}]({r['url']})" for r in ex), f"{st}회차"])
        tables.append({"title": title, "cols": [title, "상승 묶음", "전체 비율", "배율", "예시", "연속"], "rows": rows})
    sections.append({"no": "03", "title": "태그 · 장르 · 엔진 뜨는 것", "basis": ("상승 게임" if has_prev else "New & Popular 상위") + " 묶음에서 세고 전체 모집단과 비교합니다. 엔진은 '내가 만들 만한가'를 가르는 단서라 따로 셉니다.", "tables": tables})

    # 04 가격·세일
    paid = [r for r in body if not r["free"] and not r["nyop"]]
    nyop = [r for r in body if r["nyop"]]
    free = [r for r in body if r["free"]]
    sale = [r for r in body if r["sale"]]
    organic = [r for r in climbers if not r["sale"]] if has_prev else [r for r in body if r["new"] and not r["sale"]][:5]
    text = f"본문 {len(body)}개 = 유료 {len(paid)} · NYOP(원하는 만큼) {len(nyop)} · 무료 {len(free)} · 세일 중 {len(sale)}."
    sections.append({"no": "04", "title": "가격 · 세일과 상승의 관계", "basis": "itch에는 광고비가 없습니다. 세일과 무료 전환이 순위를 밀어 올리는 외부 요인이라 분리해서 봅니다.", "text": text, "blocks": [
        {"title": "오가닉 (세일 없음)", "items": [item(r) for r in organic[:5]]},
        {"title": "세일 동반", "items": [item(r) for r in ([r for r in climbers if r["sale"]] if has_prev else sale)[:5]]},
        {"title": "Top Sellers 안의 유료 신작", "items": [item(r) for r in sorted([r for r in paid if r["new"] and "top-sellers" in r["ranks"]], key=lambda r: r["ranks"]["top-sellers"])[:5]]},
    ]})

    # 05 특이사항
    jams = [r for r in body if r["jam"] and r["new"]]
    cross = [r for r in body if r["steam_url"]]
    bad = [r for r in recs.values() if not r["page_ok"]]
    exits_grow = [r for r in recs.values() if r["verdict"] == "이탈 (규모 증가)"]
    if exits_grow:
        notes.append("이탈(규모 증가) " + " · ".join(f"[{r['title']}]({r['url']}) {fmt_signed(r['rating_d1'])}" for r in exits_grow[:3]))
    if jams:
        notes.append(f"게임잼 출품 신작 {len(jams)}개: " + " · ".join(f"[{r['title']}]({r['url']})" for r in jams[:3]))
    if cross:
        notes.append(f"Steam 페이지가 있는 게임 {len(cross)}개 — 교차 등장 표는 06")
    if bad:
        notes.append(f"게임 페이지 읽기 실패 {len(bad)}개 (평점·태그 공란)")
    notes.append(f"제외 {len(recs) - len(inc)}개 · 공개일 미상 {sum(1 for r in body if not r['published'])}개 (신작 집계에서 제외)")
    sections.append({"no": "05", "title": "특이사항 · 이상현상", "basis": "", "list": notes})

    # 06 상세
    tables = []
    for ln in ("new-and-popular", "top-sellers", "popular", "top-rated", "newest"):
        rows = []
        for row in snaps[-1][1]["lists"][ln]:
            r = recs[str(row["id"])]
            p = r["prev_ranks"].get(ln)
            rows.append([
                f"{row['rank']}" + (f" ({p}→)" if p and p != row["rank"] else ""),
                f"[{r['title']}]({r['url']})" + ("" if r["included"] else " ⊘"),
                r["author"] or "—", r["genre"] or "—", ", ".join(r["made_with"]) or "—",
                price_text(r) + (" 세일" if r["sale"] else ""),
                (f"{fmt_int(r['rating'])}" + (f" ({fmt_signed(r['rating_d1'])})" if r["rating_d1"] is not None else "")) if r["rating"] is not None else "—",
                fmt_signed(r["rating_d7"]) if r["rating_d7"] is not None else "—",
                f"{r['rating_value']}★" if r["rating_value"] else "—",
                fmt_int(r["comments"]), r["status"] or "—", r["published"] or "미상",
                ", ".join(r["tags"][:3]), ("Steam" if r["steam_url"] else "") + (" 잼" if r["jam"] else ""), r["verdict"],
            ])
        tables.append({"title": f"{LIST_KO[ln]} ({len(rows)}행)",
                       "cols": ["#", "게임", "작가", "장르", "엔진", "가격", "평점 수 (1일)", f"{n7}일", "점수", "댓글", "상태", "공개", "태그", "링크", "판정"], "rows": rows})
    if cross:
        tables.append({"title": f"교차 등장 · itch 페이지에 Steam 링크가 있는 게임 ({len(cross)}개)",
                       "cols": ["게임", "Steam", "평점 수", "가격", "판정"],
                       "rows": [[f"[{r['title']}]({r['url']})", f"[{r['steam_url'].rsplit('/', 1)[-1]}]({r['steam_url']})", fmt_int(r["rating"]), price_text(r), r["verdict"]] for r in cross]})
    sections.append({"no": "06", "title": "상세", "basis": "필요할 때만 펼쳐 보십시오. ⊘ = 제외. NYOP = 원하는 만큼 지불.", "tables": tables})

    # 회차 1(비교 없음)은 오늘 목록 상위 중심, 회차 2부터는 "오늘 오른 게임" 중심 (rules.md §9 오늘의 선정 게임).
    def score_round1(r):
        s = 0
        if r["growth7"]:
            s += min(r["growth7"], 200)
        if r["new"]:
            s += 30
        if not r["sale"]:
            s += 10
        if r["made_with"]:
            s += 10
        if "new-and-popular" in r["ranks"]:
            s += max(0, 40 - r["ranks"]["new-and-popular"])
        s += min(r["rating"] or 0, 100) / 5  # 평점이 거의 없는 게임이 순위만으로 뽑히지 않게
        return s

    def score(r):
        # 주 기준: 순위 상승폭(1계단 = 1점) + 평점 수 증가율(평점 10개 이상일 때, 100% = 30점) + 평점 증가 수(50개 = 25점).
        c = r["climb"][0] or 0
        s = max(c, 0)
        if r["growth7"] and (r["rating"] or 0) >= 10:
            s += min(max(r["growth7"], 0), 100) * 0.3
        s += min(max(r["rating_d7"] or 0, 0), 50) * 0.5
        # 보조 가산점(동점 처리용): 합계 9점 = 상승폭 10계단 미만.
        if r["new"]:
            s += 4
        if not r["sale"]:
            s += 3
        if r["made_with"]:
            s += 2
        return s

    if has_prev:
        # 순위가 떨어진 게임, 순위·평점 변화가 모두 없는 게임은 후보에서 제외.
        cands = [r for r in body if (r["climb"][0] or 0) >= 0 and (r["climb"][0] or 0) + abs(r["rating_d1"] or 0) > 0]
        pick = max(cands, key=score) if cands else (climbers[0] if climbers else None)
    else:
        pick = max(body, key=score_round1) if body else None
    if pick:
        n_sel, since = state.bump("pick", pick["title"], date, prev_date)
        links = [("itch.io", pick["url"])] + ([("Steam", pick["steam_url"])] if pick["steam_url"] else [])
        pick_info = {"name": pick["title"], "url": pick["url"], "streak": n_sel, "since": since, "links": links,
                     "thumb": pick.get("thumb"), "thumb_bg": pick.get("thumb_bg"),
                     "sub": " · ".join(x for x in (pick["author"], pick["genre"], ", ".join(pick["made_with"]), ", ".join(pick["tags"][:3])) if x),
                     "line": line(pick), "badges": badges(pick)}
    else:
        pick_info = None
    if has_prev:
        for r in climbers[:2]:
            headline.append(f"[{r['title']}]({r['url']}) {LIST_KO[r['climb'][1]]} {r['prev_ranks'][r['climb'][1]]}→{r['ranks'][r['climb'][1]]}위 ▲{r['climb'][0]}"
                            + (f" · 평점 {fmt_signed(r['rating_d7'])}({n7}일)" if r["rating_d7"] is not None else " · " + line(r, with_rank=False))
                            + (" · 세일" if r["sale"] else ""))
        for r in growth[:1]:
            if r not in climbers[:2]:
                headline.append(f"[{r['title']}]({r['url']}) 평점 수 {fmt_pct(r['growth7'])} ({n7}일) · " + line(r))
    else:
        for b in sections[0]["blocks"]:
            if b["items"]:
                it = b["items"][0]
                headline.append(f"{b['title'][2:].strip()}: [{it['name']}]({it['url']}) · {it['line']}")

    n_new = sum(1 for r in body if r["new"])
    status = [("회차", f"{rn}회차"), ("비교 대상", f"{prev_date} · 1일치" if prev_date else "없음 (첫 회차)"),
              ("평점 창", f"{d7} 대비 {n7}일" if d7 else "—"), ("모집단", f"{len(recs)}개 · 본문 {len(body)}개"),
              ("신작", f"{n_new}/{len(body)}"), ("수집", snaps[-1][1]["collected_at"][:16].replace("T", " ") + " UTC")]
    n_lists_ok = sum(1 for rows in snaps[-1][1]["lists"].values() if rows)
    collect_line = f"수집 목록 {n_lists_ok}/{len(snaps[-1][1]['lists'])} 정상 · 모집단 {len(recs)} · 본문 {len(body)} · 신작 {n_new} · 페이지 실패 {len(bad)}"
    state.save()
    return {"platform": "itch", "platform_ko": "itch.io", "date": date, "round": rn, "prev_date": prev_date,
            "status": status, "pick": pick_info, "headline": headline[:3], "notes": notes[:3],
            "sections": sections, "collect_line": collect_line,
            # url → 썸네일. 03 예시처럼 링크만 있는 자리에서 렌더러가 이미지를 찾는 데 씁니다.
            "thumbs": {r["url"]: {"src": r["thumb"], "bg": r["thumb_bg"]} for r in recs.values() if r["url"] and (r["thumb"] or r["thumb_bg"])},
            "basis_line": "itch.io 목록 5개(New & Popular 108 · Top Sellers 108 · Popular 72 · Top Rated 72 · Newest 36) · 급상승 판정은 앞 3개 목록 · 신작 = 공개일 1년 이내 (공개일 미상은 집계 제외)"}
