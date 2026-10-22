"""개인 리포트 dict → Discord 임베드 payload, markdown(dry-run 본문), 이미지 카드 HTML 1장.

공용 render.py 의 썸네일·카드 CSS·날짜 표기를 그대로 가져다 씁니다(수정하지 않음).
"""
from .render import CARD_CSS, badge_cls, date_ko, esc, key_metric, thumb_html, thumb_url

COLOR = {"mine": 0x6B4FBB, "same": 0x8891A0, "week": 0x146C43}
LIM_TITLE, LIM_DESC, LIM_FIELD, LIM_FOOTER, LIM_TOTAL = 256, 4096, 1024, 2048, 6000
PLAT = {"steam": "Steam", "itch": "itch.io"}


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


# ---------- 이미지 카드 1장 (Steam · itch 내 범위 Top 3) ----------

EXTRA_CSS = """
.card::before{background:#6B4FBB}.eyebrow{color:#6B4FBB}
.body{margin-top:18px}
.sec{font-size:24px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;color:#6B4FBB;margin:16px 0 0}
.sec:first-child{margin-top:0}
.p .row{padding:11px 0;gap:22px;grid-template-columns:190px minmax(0,1fr)}
.p-itch .row{grid-template-columns:140px minmax(0,1fr)}
.p .row:first-child{border-top:0;padding-top:6px}
.p .rb{gap:2px}
.p .nm{font-size:34px;line-height:1.25;-webkit-line-clamp:1;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.p .kpi{font-size:44px;padding-top:0;line-height:1.1}
.p .cap{font-size:24px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.p .meta{font-size:22px;-webkit-line-clamp:1}
.p .rk{font-size:22px;font-weight:700;color:#8891A0;margin-right:10px}
.p-itch .th.xs{aspect-ratio:315/250;width:140px}
.same{display:inline-block;font-size:19px;color:#6B4FBB;background:#EFEBF9;border-radius:999px;padding:0 12px;margin-left:8px;vertical-align:middle;line-height:1.6}
.p .badge{font-size:19px;padding:0 12px;border-width:1.5px;margin-left:6px;vertical-align:middle;line-height:1.6}
.empty{font-size:26px;margin:14px 0}
.memo{margin-top:auto;padding-top:14px;border-top:2px solid #DDE1E8;font-size:24px;color:#4E5768;line-height:1.4;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.memo b{color:#14161C}
"""


def _rows(pl):
    if not pl["top"]:
        return f'<p class="empty">내 범위 후보 없음 (본문 {pl["counts"]["body"]} → 내 범위 {pl["counts"]["mine"]})</p>'
    rep = {"thumbs": pl.get("thumbs") or {}}
    out = []
    for i, t in enumerate(pl["top"], 1):
        hero, cap, dirn, rest = key_metric(t["line"])
        th = thumb_html(t["name"], t["url"], rep, t, cls="th xs", big=True)
        pills = "".join(f'<span class="badge {badge_cls(b)}">{esc(b)}</span>' for b in t["badges"][:1 if t["same"] else 2])
        same = f'<span class="same">{esc(t["same"])}</span>' if t["same"] else ""
        kpi = f'<div class="kpi {dirn}">{esc(hero)}</div>' if hero else ""
        capline = " · ".join(([cap] if hero and cap else []) + rest[:2])
        out.append(f'<div class="row">{th}<div class="rb"><div class="rh"><div class="nm"><span class="rk">{i}</span>{esc(t["name"])}{same}{pills}</div>{kpi}</div>'
                   + (f'<div class="cap">{esc(capline)}</div>' if capline else "")
                   + (f'<div class="meta">{esc(" · ".join(t["facts"]))}</div>' if t.get("facts") else "") + "</div></div>")
    return f'<div class="p p-{pl["platform"]}">' + "".join(out) + "</div>"


def to_card(res):
    """내 범위 Top 3 (Steam · itch) 카드 1장의 HTML."""
    body = []
    for p in ("steam", "itch"):
        pl = res["platforms"].get(p)
        body.append(f'<p class="sec">{esc(PLAT[p])}</p>' + (_rows(pl) if pl else '<p class="empty">오늘 리포트 없음</p>'))
    m = res.get("memo")
    foot_l = f"내 범위 리포트 · {date_ko(res['date'])}"
    memo = f'<div class="memo"><b>메모 · {esc(m["name"])}</b> · {esc(m["text"])}</div>' if m else ""
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>내 범위 급상승 Top 3</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap">
<style>{CARD_CSS}{EXTRA_CSS}</style></head>
<body class="personal"><div class="card">
<div class="top"><span class="eyebrow">개인 리포트 · 내 범위</span><span class="page">1 / 1</span></div>
<h1>내 범위 급상승 Top 3</h1><p class="date">{esc(date_ko(res["date"]))}</p>
<div class="body">{"".join(body)}{memo}</div>
<div class="foot"><span>{esc(foot_l)}</span><span>indie-trending · personal</span></div>
</div></body></html>"""
