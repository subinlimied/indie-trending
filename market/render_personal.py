"""개인 리포트 dict → Discord 임베드 payload, markdown(dry-run 본문), 이미지 카드 HTML 1장.

임베드와 markdown 은 그대로이고, 카드만 design/tokens.json + market/ui.py + market/charts.py 를 씁니다:
내 범위 Top 3(Steam·itch 합쳐 썸네일 · 이름 · 핵심 델타 칩) + 가격 × 플레이 시간 산점도(선정 게임 강조, 플레이 시간 미상은 점선 줄) + 제작 메모 한 줄.
"""
from . import charts, headline, render, ui
from .render import badge_cls, date_ko, esc, key_metric, thumb_html, thumb_url

COLOR = {"mine": 0x6B4FBB, "same": 0x8891A0, "week": 0x146C43}
LIM_TITLE, LIM_DESC, LIM_FIELD, LIM_FOOTER, LIM_TOTAL = 256, 4096, 1024, 2048, 6000
PLAT = {"steam": "Steam", "itch": "itch.io"}
TAG = "Indie Trending · Personal"


def clip(s, n):
    s = (s or "").strip()
    return s if len(s) <= n else s[: max(0, n - 1)].rstrip() + "…"


def _watch_lines(res):
    wl = res.get("watchlist") or []
    if not wl:
        return ("비어 있음 — profile.json 의 watchlist.steam 에 appid, watchlist.itch 에 게임 id 를 넣으면 매일 변화를 보여 줍니다.")
    out = []
    for w in wl:
        if w["name"]:
            tag = "내 범위" if w["in_range"] else ("밖: " + ", ".join(w["reasons"]) if w["reasons"] else "밖")
            out.append(f"• [{w['name']}]({w['url']}) ({PLAT[w['platform']]}) · {w['line']} · {tag}")
        else:
            out.append(f"• {PLAT[w['platform']]} {w['id']} · {w['line']}")
    return "\n".join(out)


def _top_lines(pl):
    if not pl["top"]:
        return f"내 범위 후보가 없습니다 (본문 {pl['counts']['body']}개 중 내 범위 {pl['counts']['mine']}개)."
    lines = []
    for i, t in enumerate(pl["top"], 1):
        extra = " · ".join(t["badges"][:3] + ([t["same"]] if t["same"] else []))
        lines.append(f"**{i}. [{t['name']}]({t['url']})** · {t['line']}" + (f"\n{extra}" if extra else ""))
    return "\n".join(lines)


def _platform_embed(pl):
    e = {"title": clip(f"{pl['platform_ko']} · 내 범위 급상승 Top 3 · {pl['round']}회차", LIM_TITLE), "color": COLOR["mine"],
         "description": clip(_top_lines(pl), LIM_DESC), "fields": []}
    if pl["top"]:
        t = pl["top"][0]
        e["url"] = t["url"]
        img = thumb_url(t["url"], {"thumbs": pl.get("thumbs") or {}}, t)
        if img:
            e["image"] = {"url": img}
    if pl["why"] and not pl["same_as_public"]:
        e["fields"].append({"name": "공용과 다른 점", "value": clip(pl["why"], LIM_FIELD), "inline": False})
    if pl["pushed"]:
        v = "\n".join(f"• [{p['name']}]({p['url']}) ({p['role']}) — {', '.join(p['reasons'])}" for p in pl["pushed"][:4])
        e["fields"].append({"name": "내 범위 밖으로 밀린 공용 게임", "value": clip(v, LIM_FIELD), "inline": False})
    foot = f"본문 {pl['counts']['body']}개 → 내 범위 {pl['counts']['mine']}개"
    if pl["fail_line"]:
        foot += f" · 밀린 이유: {pl['fail_line']}"
    e["footer"] = {"text": clip(foot, LIM_FOOTER)}
    if not e["fields"]:
        del e["fields"]
    return e


def _memo_embed(res):
    m = res.get("memo")
    desc = (f"**[{m['name']}]({m['url']})** ({PLAT[m['platform']]})\n{m['text']}" if m else "오늘은 내 범위 1위 게임이 없어 메모가 없습니다.")
    return {"title": "제작 관점 메모 · watchlist", "color": COLOR["mine"], "description": clip(desc, LIM_DESC),
            "fields": [{"name": "watchlist", "value": clip(_watch_lines(res), LIM_FIELD), "inline": False}]}


def _weekly_embed(w):
    combos = "\n".join(f"{i}. {' + '.join(c['tags'])} · {c['n']}회" for i, c in enumerate(w["combos"], 1)) or "데이터 없음"
    fast = "\n".join(f"{i}. [{f['name']}]({f['url']}) ({PLAT[f['platform']]}) · 일 평균 +{f['rate']:g} · 누적 {f['reviews']:,}"
                     + (f" · 출시 {f['age']}일" if f.get("age") is not None else "") + f" · {f['basis']}"
                     for i, f in enumerate(w["fast"], 1)) or "출시 90일 이내 내 범위 신작 중 리뷰가 늘어난 게임이 없습니다."
    return {"title": clip(f"이번 주 내 범위 · {w['days']}일치 ({w['from']} ~ {w['to']})", LIM_TITLE), "color": COLOR["week"],
            "description": "내 범위 Top 3 에 오른 게임의 태그 조합과, 출시 90일 이내 신작의 리뷰(평점) 증가 속도입니다.",
            "fields": [{"name": "가장 자주 오른 태그 조합 Top 3", "value": clip(combos, LIM_FIELD), "inline": False},
                       {"name": "리뷰가 가장 빨리 쌓인 신작 3개", "value": clip(fast, LIM_FIELD), "inline": False}]}


def build_payload(res):
    """개인 리포트 dict → Discord payload. 공용과 완전히 같으면 짧은 임베드 1개(+주간)."""
    plats = res["platforms"]
    content = f"**내 범위 리포트 · {date_ko(res['date'])}**"
    if res["same_as_public"]:
        m = res.get("memo")
        desc = "Steam · itch 모두 내 범위 Top 3 가 공용 리포트의 선정·Top 3 와 같습니다. 공용 리포트를 보십시오."
        if m:
            desc += f"\n\n메모 · [{m['name']}]({m['url']}): {m['text']}"
        desc += "\n\nwatchlist: " + _watch_lines(res)
        embeds = [{"title": clip(f"내 범위 리포트 · 공용과 동일 · {date_ko(res['date'])}", LIM_TITLE), "color": COLOR["same"], "description": clip(desc, LIM_DESC)}]
        content += " · 공용과 동일"
    else:
        embeds = [_platform_embed(plats[p]) for p in ("steam", "itch") if p in plats]
        embeds.append(_memo_embed(res))
    if res.get("weekly"):
        embeds.append(_weekly_embed(res["weekly"]))
    return {"content": clip(content, 2000), "embeds": embeds, "allowed_mentions": {"parse": []}}


# ---------- markdown (dry-run 본문) ----------

def to_md(res):
    out = [f"# 내 범위 리포트 · {date_ko(res['date'])}" + (" · 공용과 동일" if res["same_as_public"] else ""), ""]
    for p in ("steam", "itch"):
        pl = res["platforms"].get(p)
        if not pl:
            out.append(f"## {PLAT[p]} · 리포트 없음\n")
            continue
        out.append(f"## {pl['platform_ko']} · 내 범위 급상승 Top 3 · {pl['round']}회차")
        out.append(_top_lines(pl))
        if pl["why"]:
            out.append(f"\n- 공용과 다른 점: {pl['why']}")
        for q in pl["pushed"]:
            out.append(f"- 밀린 공용 게임: [{q['name']}]({q['url']}) ({q['role']}) — {', '.join(q['reasons'])}")
        out.append(f"- 본문 {pl['counts']['body']}개 → 내 범위 {pl['counts']['mine']}개" + (f" · 밀린 이유: {pl['fail_line']}" if pl["fail_line"] else ""))
        out.append("")
    m = res.get("memo")
    out.append("## 제작 관점 메모")
    out.append(f"[{m['name']}]({m['url']}) ({PLAT[m['platform']]}): {m['text']}" if m else "없음")
    out.append("\n## watchlist")
    out.append(_watch_lines(res))
    w = res.get("weekly")
    if w:
        out.append(f"\n## 이번 주 내 범위 · {w['days']}일치 ({w['from']} ~ {w['to']})")
        out.append("태그 조합 Top 3:")
        out += [f"{i}. {' + '.join(c['tags'])} · {c['n']}회" for i, c in enumerate(w["combos"], 1)] or ["- 없음"]
        out.append("리뷰가 빨리 쌓인 신작:")
        out += [f"{i}. [{f['name']}]({f['url']}) · 일 평균 +{f['rate']:g} · 누적 {f['reviews']:,} · {f['basis']}" for i, f in enumerate(w["fast"], 1)] or ["- 없음"]
    return "\n".join(out) + "\n"


# ---------- 이미지 카드 1장 ----------

CARD_CSS = """
.rows{display:flex;flex-direction:column;background:var(--surface);border:var(--bw) solid var(--line)}
.row{display:grid;grid-template-columns:auto auto minmax(0,1fr) auto;gap:16px;align-items:center;padding:12px 16px;border-top:var(--bw) solid var(--line)}
.row:first-child{border-top:0}
.row .th{display:block;border:var(--bw) solid var(--line-strong);background-color:hsl(var(--h,220) var(--ph-s) var(--ph-l));background-size:cover;background-position:center;width:150px;aspect-ratio:616/353}
.row .th.itch{width:100px;aspect-ratio:315/250}
.row .nm{margin:0;font:var(--t-headline-md-w) var(--t-headline-md) var(--font-display);letter-spacing:var(--t-headline-md-ls);text-transform:uppercase;color:var(--ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .cap{font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);letter-spacing:var(--t-data-md-ls);color:var(--ink-2);margin:4px 0 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.row .cap .same{color:var(--primary-light)}
.row .big{display:flex;flex-direction:column;align-items:flex-end;gap:4px}
.row .big .delta{font:700 var(--t-data-lg) var(--font-mono);letter-spacing:var(--t-data-lg-ls)}
.row .big small{font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink-2);text-align:right;max-width:16ch}
.memo{display:flex;gap:12px;align-items:baseline;font:var(--t-body-md-w) var(--t-body-md) var(--font-body);color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.memo b{color:var(--ink);font-family:var(--font-mono);flex:none}
"""


def merged_top(res, n=3):
    """Steam·itch 내 범위 Top 을 점수순으로 합쳐 n개."""
    items = []
    for p in ("steam", "itch"):
        pl = res["platforms"].get(p)
        for t in (pl or {}).get("top", []):
            items.append((t.get("score") or 0, p, t, {"thumbs": pl.get("thumbs") or {}}))
    items.sort(key=lambda x: -x[0])
    return items[:n]


def _row(i, platform, t, rep):
    hero, cap, dirn, rest = key_metric(t["line"])
    th = thumb_html(t["name"], t["url"], rep, t, cls="th" + (" itch" if platform == "itch" else ""), big=True)
    facts = " · ".join((t.get("facts") or [])[:4])
    same = f'<span class="same">{esc(t["same"])}</span> · ' if t.get("same") else ""
    big = (f'<div class="big"><span class="delta {dirn}">{esc(hero)}</span>' + (f'<small>{esc(cap)}</small>' if cap else "") + "</div>") if hero else ""
    return (f'<div class="row"><span class="rank{" top" if i <= 3 else ""}">{i:02d}</span>{th}<div><h3 class="nm">{esc(t["name"])}</h3>'
            f'<p class="cap">{same}{esc(PLAT[platform])} · {esc(facts)}</p></div>{big}</div>')


def _scatter(res, width, height):
    prof = res.get("profile") or {}
    pts = []
    for p in ("steam", "itch"):
        pl = res["platforms"].get(p) or {}
        for g in pl.get("scatter") or []:
            if g.get("price_usd") is None:
                continue
            kind = "pick" if g.get("top") == 1 else "hi" if g.get("top") else ""
            pts.append((g["name"], g["price_usd"], g.get("playtime_h"), 1, kind))
    quad = None
    if prof.get("max_price_usd") and prof.get("max_playtime_hours"):
        quad = {"x": prof["max_price_usd"], "y": prof["max_playtime_hours"], "label": ""}
    return charts.scatter(pts, width=width, height=height, scale="card", x_kind="usd", y_kind="hours", x_label="정가 (USD)", y_label="평균 플레이 시간",
                          none_label="시간 미상", title="가격 × 플레이 시간", size_range=(6, 6), label_chars=18, quadrant=None), len(pts)


def to_card(res, link=None):
    """내 범위 카드 1장의 HTML."""
    w = ui.tokens()["카드"]["폭"] - 2 * ui.tokens()["간격"]["카드_여백"]
    tops = merged_top(res)
    counts = " · ".join(f"{PLAT[p]} {res['platforms'][p]['counts']['mine']}/{res['platforms'][p]['counts']['body']}" for p in ("steam", "itch") if p in res["platforms"])
    if tops:
        _, p1, t1, _ = tops[0]
        hl = headline.to_html(headline.personal_top(t1, 1))
    else:
        hl = "오늘은 내 범위 후보가 없습니다"
    rows = "".join(_row(i, p, t, rep) for i, (_, p, t, rep) in enumerate(tops, 1)) or '<p class="empty" style="padding:16px">내 범위 후보 없음</p>'
    svg, n_pts = _scatter(res, w - 48, 400)
    m = res.get("memo")
    memo = f'<div class="memo"><b>MEMO</b><span><b style="font-family:var(--font-body)">{esc(m["name"])}</b> · {esc(m["text"])}</span></div>' if m else ""
    body = (f'<div class="cardtitle"><div class="kick"><span class="lchip pos">MY RANGE</span><span class="seclabel">profile.json 기준 내 범위 · {esc(counts)}</span></div>'
            f'<h1 class="hl">{hl}</h1></div>'
            f'<div class="rows">{rows}</div>'
            f'<div class="chartp" style="flex:0 0 auto"><div class="ph"><p class="seclabel strong">가격 × 플레이 시간 · 내 범위 {n_pts}개</p><p class="seclabel">초록 = 내 범위 Top 3 · 흰 테두리 = 1위 · 아래 점선 = 플레이 시간 미상</p></div>'
            f'<div class="body">{svg}</div></div>{memo}')
    return render.card_page("personal", TAG, "My Range", f"{date_ko(res['date'])}", None, body, 1, 1, link,
                            fallback_see=f"내 범위 리포트 · {date_ko(res['date'])} · 비공개", extra_css=CARD_CSS, title="내 범위 리포트")
