"""미디어·밈 리포트 dict → markdown(dry-run 본문) · HTML(01~07) · 카드 HTML 2장 · Discord 임베드.

HTML 은 render.py 의 CSS 토큰(색·서체·카드·배지)을 그대로 쓰고 미디어용 규칙만 덧붙입니다.
KYM·Reddit 제목과 요약은 영어 원문 그대로 두고 번역하지 않습니다.
"""
import html as H
from datetime import datetime, timezone, timedelta

from .render import CSS, CARD_CSS, date_ko, esc

KST = timezone(timedelta(hours=9))
TITLE = "미디어·밈 트렌드"
SECTIONS = [("01", "오늘의 밈·숏폼 트렌드", "KYM"), ("02", "검색 급상승", "KR / US"), ("03", "세상의 관심사", "위키 en / ko"),
            ("04", "커뮤니티 베스트", "Reddit"), ("05", "밈 템플릿 순위 변동", "Imgflip"), ("06", "게임 ↔ 밈 교차", "Steam · itch"),
            ("07", "수집 상태", "")]
SUMMARY_LEN = 120
COLOR = 0x6B3FA0

MEDIA_CSS = """
.pick .pk-img img{width:100%;max-width:360px;border-radius:6px;display:block}
.pk-sum{margin:0;font-size:15px;color:var(--ink);line-height:1.55}
.g .im{width:120px;height:120px;border-radius:6px;object-fit:cover;background:var(--surface-2);flex:none;display:block}
.g .im.sq{width:72px;height:72px}
.g .nm a{color:inherit}
.rk{font-family:var(--mono);font-size:14px;color:var(--faint);min-width:2.2ch;text-align:right;padding-top:3px}
.g.r{grid-template-columns:auto minmax(0,1fr) auto}
.g.r .nm{font-weight:500}
.trf{font-variant-numeric:tabular-nums;white-space:nowrap}
.src-ok{color:var(--rise);font-weight:600}.src-fail{color:var(--fall);font-weight:600}
td.wrap{white-space:normal}
.pc{display:flex;flex-wrap:wrap;gap:8px}
.pc .tile{min-width:110px}
"""

PLATFORM_CLS = {"TikTok": "acc", "Twitter/X": "", "Reddit": "disc", "YouTube": "excl", "Instagram": "new", "Twitch": "acc"}


def _sum(s, n=SUMMARY_LEN):
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _fmt_traffic(x):
    return x.get("traffic_raw") or (f"{x.get('traffic', 0):,}+" if x.get("traffic") else "—")


def _arrow(d):
    if d is None:
        return ""
    if d > 0:
        return f"▲{d}"
    if d < 0:
        return f"▼{-d}"
    return "—"


def _pub_kst(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(KST).strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        return iso or ""


def _mdsafe(s):
    return (s or "").replace("[", "［").replace("]", "］").replace("*", "＊").replace("_", "＿").replace("`", "'")


def _cross_line(c):
    return f"{c['term']} → {c['game']} ({'Steam' if c['platform'] == 'steam' else 'itch'}) · {c['source']}"


# ====================================================================
# markdown (dry-run 본문)
# ====================================================================

def to_md(rep):
    L = [f"# {TITLE} · {date_ko(rep['date'])} · {rep['round']}회차", ""]
    p = rep.get("pick")
    if p:
        streak = f" · {p['streak']}일 연속" if p.get("streak", 1) > 1 else ""
        L.append(f"**오늘의 트렌드 → [{p['title']}]({p['url']})**{streak} · {' · '.join(p.get('platforms') or []) or '플랫폼 미상'}")
        if p.get("summary"):
            L.append(f"> {_sum(p['summary'])}")
    else:
        L.append("오늘의 트렌드: KYM 기사 없음")
    L.append("플랫폼 집계: " + (" · ".join(f"{a} {n}건" for a, n in rep["platform_counts"]) or "없음") + f" · KYM {len(rep['kym'])}건 (신규 {rep['kym_new']})")
    L.append("")
    L.append("## 01 오늘의 밈·숏폼 트렌드 (KYM)")
    for x in rep["kym"][:12]:
        tag = " · ".join(x.get("platforms") or [])
        L.append(f"- [{x['title']}]({x['url']})" + (f" · {tag}" if tag else "") + (" · 신규" if x.get("new") else "") + f" · {_pub_kst(x.get('published'))}")
    L.append("")
    L.append("## 02 검색 급상승")
    for geo in ("KR", "US"):
        L.append(f"**{geo}**")
        for x in rep["trends"][geo]:
            L.append(f"{x['rank']}. {x['title']} · {_fmt_traffic(x)}" + (f" · {x['days']}일 연속" if x.get("days", 1) > 1 else "") + (f" · {x['news_title']}" if x.get("news_title") else ""))
    L.append("")
    L.append("## 03 세상의 관심사 (위키)")
    for proj in ("en", "ko"):
        L.append(f"**{proj}** ({rep['wiki'].get(proj + '_day', '')})")
        for x in rep["wiki"][proj][:10]:
            L.append(f"{x['rank']}. {x['title']} · {x['views']:,}" + (f" · {x['days']}일 연속" if x.get("days", 1) > 1 else ""))
    L.append("")
    L.append("## 04 커뮤니티 베스트 (Reddit)")
    for r in rep["reddit"]:
        if r["status"] != "ok":
            L.append(f"- r/{r['sub']}: 실패 ({r.get('error', '')})")
            continue
        L.append(f"**r/{r['sub']}**")
        for x in r["items"][:5]:
            L.append(f"- [{x['title']}]({x['url']})")
    L.append("")
    L.append("## 05 밈 템플릿 순위 변동 (Imgflip)")
    im = rep["imgflip"]
    if im["compared"]:
        for x in im["movers"][:10]:
            L.append(f"- {x['name']} {x['prev_rank']}→{x['rank']}위 {_arrow(x['delta'])}")
        L.append("신규 진입: " + (", ".join(f"{x['name']}({x['rank']}위)" for x in im["entered"]) or "없음"))
        L.append("이탈: " + (", ".join(f"{x['name']}(어제 {x['prev_rank']}위)" for x in im["exited"]) or "없음"))
    else:
        L.append("비교 대상 없음 (회차 1). 오늘 상위: " + ", ".join(x["name"] for x in im["items"][:10]))
    L.append("")
    L.append("## 06 게임 ↔ 밈 교차")
    L += [f"- {_cross_line(c)}" for c in rep["cross"]] or ["- 없음"]
    L.append("")
    L.append("## 07 수집 상태")
    L += [f"- {s['label']}: {'정상' if s['status'] == 'ok' else '실패'} · {s['count']}개" + (f" · {s['error']}" if s.get("error") else "") for s in rep["sources"]]
    L.append("")
    L.append(rep["collect_line"])
    return "\n".join(L) + "\n"


# ====================================================================
# HTML
# ====================================================================

def _a(text, url):
    return f'<a href="{H.escape(url or "", quote=True)}" target="_blank" rel="noopener">{esc(text)}</a>' if url else esc(text)


def _pills(platforms, extra=()):
    out = [f'<span class="badge {PLATFORM_CLS.get(p, "")}">{esc(p)}</span>' for p in platforms or []]
    out += [f'<span class="badge new">{esc(e)}</span>' for e in extra if e]
    return f'<div class="pills">{"".join(out)}</div>' if out else ""


def _pick_html(p):
    if not p:
        return '<div class="card side"><p class="lbl">오늘의 트렌드</p><p class="empty">최근 48시간 KYM 기사가 없습니다.</p></div>'
    streak = f" · {p['streak']}일 연속" if p.get("streak", 1) > 1 else ""
    img = f'<img src="{H.escape(p["image"], quote=True)}" alt="">' if p.get("image") else ""
    return (f'<div class="card pick"><div class="pk-img">{img}</div><div class="pk-body"><p class="lbl">오늘의 트렌드{esc(streak)} · {esc(p.get("reason", ""))}</p>'
            f'<h2 class="pk-name" style="font-size:24px">{_a(p["title"], p["url"])}</h2>'
            f'<p class="pk-sum">{esc(p.get("summary", ""))}</p>{_pills(p.get("platforms"), ["신규" if p.get("new") else ""])}'
            f'<p class="pk-sub">KYM · {esc(_pub_kst(p.get("published")))} KST</p></div></div>')


def _side_html(rep):
    tiles = "".join(f'<dl class="tile"><dt>{esc(a)}</dt><dd>{n}<small>건</small></dd></dl>' for a, n in rep["platform_counts"][:6])
    tiles = tiles or '<p class="empty">제목에 플랫폼 단서가 있는 기사가 없습니다.</p>'
    quick = []
    for geo in ("KR", "US"):
        top = rep["trends"][geo][:3]
        quick.append(f'<li class="nothumb"><div class="h1">검색 급상승 {geo}</div><div class="h2">' + "".join(f"<span>{esc(x['title'])} {esc(_fmt_traffic(x))}</span>" for x in top) + "</div></li>")
    return (f'<div class="card side"><div><p class="lbl">플랫폼 집계 · KYM {len(rep["kym"])}건 · 신규 {rep["kym_new"]}</p><div class="pc tiles">{tiles}</div></div>'
            f'<div><ul class="hl">{"".join(quick)}</ul></div></div>')


def _kym_html(rep):
    rows = []
    for x in rep["kym"]:
        im = f'<img class="im" src="{H.escape(x["image"], quote=True)}" alt="" loading="lazy">' if x.get("image") else '<span class="im"></span>'
        rows.append(f'<div class="g">{im}<div class="gb"><div class="gh"><div class="nm">{_a(x["title"], x["url"])}</div></div>'
                    f'<div class="sub">{esc(_sum(x.get("summary"), 200))}</div>{_pills(x.get("platforms"), ["신규" if x.get("new") else ""])}'
                    f'<div class="meta"><span>{esc(_pub_kst(x.get("published")))} KST</span></div></div></div>')
    return f'<div class="card block">{"".join(rows)}</div>' if rows else '<p class="empty">최근 48시간 기사가 없습니다.</p>'


def _rank_rows(items, line):
    rows = []
    for x in items:
        rows.append(f'<div class="g r"><div class="rk">{x["rank"]}</div>{line(x)}</div>')
    return "".join(rows) or '<p class="empty">없음</p>'


def _trend_row(x):
    days = f'<span class="badge acc">{x["days"]}일 연속</span>' if x.get("days", 1) > 1 else ""
    return (f'<div class="gb"><div class="nm">{_a(x["title"], x["url"])} {days}</div>'
            + (f'<div class="sub">{_a(x["news_title"], x["news_url"])}</div>' if x.get("news_title") else "") + f'</div><div class="kpi"><b class="trf">{esc(_fmt_traffic(x))}</b></div>')


def _wiki_row(x):
    delta = x["prev_rank"] - x["rank"] if x.get("prev_rank") else None
    bits = [f'<span class="badge acc">{x["days"]}일 연속</span>' if x.get("days", 1) > 1 else "", f'<span class="{"up" if (delta or 0) > 0 else "down" if (delta or 0) < 0 else ""}">{_arrow(delta)}</span>' if delta is not None else ""]
    return f'<div class="gb"><div class="nm">{_a(x["title"], x["url"])} {" ".join(b for b in bits if b)}</div></div><div class="kpi"><b>{x["views"]:,}</b><small>조회</small></div>'


def _two_blocks(rep, key, labels, row, day=None):
    out = []
    for k, lbl in labels:
        d = (f" · {rep['wiki'].get(k + '_day', '')} 집계" + (" (전날과 같은 집계)" if rep['wiki'].get(k + '_same') else "")) if day else ""
        out.append(f'<div class="card block"><h4>{esc(lbl)}{esc(d)}</h4>{_rank_rows(rep[key][k], row)}</div>')
    return f'<div class="blocks">{"".join(out)}</div>'


def _reddit_html(rep):
    out = []
    for r in rep["reddit"]:
        if r["status"] != "ok":
            body = f'<p class="empty">수집 실패 · {esc(r.get("error", ""))}</p>'
        else:
            body = "".join(f'<div class="g r"><div class="rk">{x["rank"]}</div><div class="gb"><div class="nm">{_a(x["title"], x["url"])}</div></div></div>' for x in r["items"])
        out.append(f'<div class="card block"><h4>r/{esc(r["sub"])}</h4>{body}</div>')
    return f'<div class="blocks">{"".join(out)}</div>'


def _imgflip_html(rep):
    im = rep["imgflip"]

    def row(x, cap):
        d = x.get("delta")
        kpi = f'<div class="kpi {"up" if (d or 0) > 0 else "down" if (d or 0) < 0 else ""}"><b>{esc(_arrow(d)) if d is not None else ("신규" if x.get("new") else "—")}</b><small>{esc(cap)}</small></div>'
        return (f'<div class="g"><img class="im sq" src="{H.escape(x["url"], quote=True)}" alt="" loading="lazy"><div class="gb"><div class="gh"><div class="nm">{x["rank"]}. {_a(x["name"], x["url"])}</div>{kpi}</div></div></div>')

    if not im["compared"]:
        top = "".join(row(x, "") for x in im["items"][:10])
        return f'<p class="stext">비교 대상이 없습니다(회차 1). 오늘 순위만 보여 줍니다.</p><div class="card block">{top}</div>'
    movers = "".join(row(x, f"{x['prev_rank']}→{x['rank']}위") for x in im["movers"][:10]) or '<p class="empty">상위 30 안에서 순위 변동이 없습니다.</p>'
    entered = ", ".join(f"{esc(x['name'])} ({x['rank']}위)" for x in im["entered"]) or "없음"
    exited = ", ".join(f"{esc(x['name'])} (어제 {x['prev_rank']}위)" for x in im["exited"]) or "없음"
    table = "".join(f'<tr><td class="num">{x["rank"]}</td><td class="wrap">{_a(x["name"], x["url"])}</td><td class="num">{x["prev_rank"] or "—"}</td><td class="num {"up" if (x["delta"] or 0) > 0 else "down" if (x["delta"] or 0) < 0 else ""}">{esc(_arrow(x["delta"]) if x["delta"] is not None else "신규")}</td><td class="num">{(x.get("captions") or 0):,}</td></tr>' for x in im["items"])
    return (f'<div class="blocks"><div class="card block"><h4>순위 변동 Top 10 (상위 {len(im["items"])} 안)</h4>{movers}</div>'
            f'<div class="card block"><h4>신규 진입 · 이탈 (100개 기준)</h4><p class="stext"><b>신규 진입</b> {entered}</p><p class="stext"><b>이탈</b> {exited}</p></div></div>'
            f'<details class="dt"><summary>상위 {len(im["items"])} 전체</summary><div class="tbl"><table><thead><tr><th class="num">#</th><th>템플릿</th><th class="num">어제</th><th class="num">변동</th><th class="num">캡션 수</th></tr></thead><tbody>{table}</tbody></table></div></details>')


def _cross_html(rep):
    if not rep["cross"]:
        return '<p class="empty">오늘은 검색·위키·Reddit 제목과 겹치는 Steam·itch 게임이 없습니다.</p>'
    rows = "".join(f'<div class="g r"><div class="rk">{i}</div><div class="gb"><div class="nm">{_a(c["term"], c["url"])} → {_a(c["game"], c["game_url"])} <span class="badge {"acc" if c["platform"] == "steam" else "disc"}">{"Steam" if c["platform"] == "steam" else "itch"}</span></div><div class="sub">{esc(c["source"])}</div></div></div>' for i, c in enumerate(rep["cross"], 1))
    return f'<div class="card block">{rows}</div>'


def _status_html(rep):
    rows = "".join(f'<tr><td>{esc(s["label"])}</td><td class="{"src-ok" if s["status"] == "ok" else "src-fail"}">{"정상" if s["status"] == "ok" else "실패"}</td><td class="num">{s["count"]}</td><td class="wrap">{esc(s.get("error", ""))}</td></tr>' for s in rep["sources"])
    return f'<div class="tbl solo"><table><thead><tr><th>소스</th><th>상태</th><th class="num">개수</th><th>비고</th></tr></thead><tbody>{rows}</tbody></table></div>'


def to_html(rep):
    bodies = {
        "01": _kym_html(rep),
        "02": _two_blocks(rep, "trends", [("KR", "한국"), ("US", "미국")], _trend_row),
        "03": _two_blocks(rep, "wiki", [("en", "영어 위키백과"), ("ko", "한국어 위키백과")], _wiki_row, day=True),
        "04": _reddit_html(rep), "05": _imgflip_html(rep), "06": _cross_html(rep), "07": _status_html(rep),
    }
    secs = "".join(f'<section id="s{no}"><h2><span class="no">{no}</span>{esc(t)}' + (f' <small style="color:var(--muted);font-weight:500">{esc(sub)}</small>' if sub else "") + f"</h2>{bodies[no]}</section>" for no, t, sub in SECTIONS)
    toc = "".join(f'<a href="#s{no}"><b>{no}</b>{esc(t)}</a>' for no, t, _ in SECTIONS)
    status = "".join(f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in rep["status"] if v not in (None, "", "—"))
    basis = "".join(f"<li>{esc(x)}</li>" for x in rep["basis_line"].split(" · "))
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(TITLE)} · {esc(rep['date'])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap">
<style>{CSS}{MEDIA_CSS}</style></head>
<body class="media"><div class="wrap">
<header><p class="eyebrow">미디어·밈 리포트 · {rep['round']}회차</p><h1>{esc(TITLE)} · {date_ko(rep['date'])}</h1>
<ul class="basis">{basis}</ul><dl class="status">{status}</dl></header>
<nav class="toc">{toc}</nav>
<div class="top">{_pick_html(rep.get("pick"))}{_side_html(rep)}</div>
{secs}
<footer>{esc(rep['collect_line'])} · 생성 {datetime.now().strftime('%Y-%m-%d %H:%M')}<br>KYM·Reddit 제목과 요약은 원문 그대로입니다. 검색량은 Google 트렌드의 대략값입니다.</footer>
</div></body></html>"""


# ====================================================================
# 이미지 카드 (1080×1350 × 2장)
# ====================================================================

MEDIA_CARD_CSS = """
.card::before{background:#6B3FA0}.eyebrow{color:#6B3FA0}
.ttl{font-size:44px;line-height:1.2;font-weight:700;margin:14px 0 8px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.sum{font-size:26px;color:#4E5768;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;margin:0}
.badge.tk{color:#6B3FA0;border-color:transparent;background:#EFE6FA}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:36px;margin-top:6px}
.tiles.sm{margin-top:18px}.tiles.sm .tile{padding:14px 20px 12px}.tiles.sm .tile dd{font-size:46px}.tiles.sm .tile dt,.tiles.sm .tile dd small{font-size:23px}.pills{margin-top:10px}
.cols h3{font-size:30px;margin:0 0 8px;color:#6B3FA0}
.ln{display:grid;grid-template-columns:40px minmax(0,1fr) auto;gap:10px;align-items:baseline;padding:7px 0;border-top:2px solid #DDE1E8;font-size:28px;line-height:1.3}
.ln:first-of-type{border-top:0}
.ln .r{color:#BFC6D1;font-weight:700;font-variant-numeric:tabular-nums}
.ln .t{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:500}
.ln .v{color:#4E5768;font-size:24px;white-space:nowrap;font-variant-numeric:tabular-nums}
.mv{display:grid;grid-template-columns:96px minmax(0,1fr) auto;gap:22px;align-items:center;padding:13px 0;border-top:2px solid #DDE1E8}
.mv:first-of-type{border-top:0;padding-top:6px}
.mv img{width:96px;height:96px;object-fit:cover;border-radius:12px;background:#DDE1E8}
.mv .nm{font-size:34px;line-height:1.25;display:-webkit-box;-webkit-line-clamp:1;-webkit-box-orient:vertical;overflow:hidden}
.mv .kpi{font-size:52px}
.mv .cap{font-size:26px}
.xr{padding:14px 0;border-top:2px solid #DDE1E8;font-size:30px;line-height:1.35}
.xr .tm{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.xr:first-of-type{border-top:0;padding-top:6px}
.xr small{display:block;font-size:26px;color:#8891A0}
.sec{margin-top:26px}
"""


def _card(body, rep, i, n, title, eyebrow):
    foot = f"{TITLE} · {date_ko(rep['date'])} · {rep['round']}회차"
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap">
<style>{CARD_CSS}{MEDIA_CARD_CSS}</style></head>
<body class="media"><div class="card">
<div class="top"><span class="eyebrow">{esc(eyebrow)}</span><span class="page">{i} / {n}</span></div>
<h1>{esc(title)}</h1><p class="date">{esc(date_ko(rep["date"]))}</p>
<div class="body">{body}</div>
<div class="foot"><span>{esc(foot)}</span><span>indie-trending</span></div>
</div></body></html>"""


def _cover_body(rep):
    p = rep.get("pick")
    if p:
        streak = f" · {p['streak']}일 연속" if p.get("streak", 1) > 1 else ""
        pills = "".join(f'<span class="badge {"tk" if a == "TikTok" else badge_cls(a)}">{esc(a)}</span>' for a in (p.get("platforms") or [])[:4])
        head = (f'<p class="lbl">오늘의 트렌드{esc(streak)}</p><h2 class="ttl">{esc(p["title"])}</h2><p class="sum">{esc(_sum(p.get("summary"), 160))}</p>'
                + (f'<div class="pills">{pills}</div>' if pills else ""))
    else:
        head = '<p class="lbl">오늘의 트렌드</p><p class="empty">최근 48시간 KYM 기사가 없습니다.</p>'
    pc = rep["platform_counts"][:2]
    tiles = [("KYM 기사 · 48시간", f"{len(rep['kym'])}", f"신규 {rep['kym_new']}건" if rep.get("prev_date") else "회차 1")]
    tiles += [(a, f"{n}", "건") for a, n in pc]
    if len(tiles) < 3:
        im = rep["imgflip"]
        tiles.append(("밈 템플릿 신규 진입", f"{len(im['entered'])}" if im["compared"] else "—", f"이탈 {len(im['exited'])}" if im["compared"] else "비교 없음"))
    while len(tiles) < 3:
        tiles.append(("플랫폼 단서", "—", ""))
    tiles_html = "".join(f'<dl class="tile"><dt>{esc(l)}</dt><dd>{esc(v)}' + (f"<small>{esc(s)}</small>" if s else "") + "</dd></dl>" for l, v, s in tiles[:3])
    cols = []
    for geo in ("KR", "US"):
        rows = "".join(f'<div class="ln"><span class="r">{x["rank"]}</span><span class="t">{esc(x["title"])}</span><span class="v">{esc(_fmt_traffic(x))}</span></div>' for x in rep["trends"][geo][:5]) or '<p class="empty" style="font-size:28px;margin:10px 0">수집 실패</p>'
        cols.append(f"<div><h3>{geo}</h3>{rows}</div>")
    return head + f'<div class="tiles sm">{tiles_html}</div><div class="sec"><p class="lbl">검색 급상승 Top 5</p><div class="cols">{"".join(cols)}</div></div>'


def badge_cls(p):
    return PLATFORM_CLS.get(p, "")


def _second_body(rep):
    im = rep["imgflip"]
    if im["compared"]:
        rows = im["movers"][:5]
        body = "".join(f'<div class="mv"><img src="{H.escape(x["url"], quote=True)}" alt=""><div><div class="nm">{esc(x["name"])}</div><div class="cap">{x["prev_rank"]}→{x["rank"]}위</div></div><div class="kpi {"up" if x["delta"] > 0 else "down"}">{esc(_arrow(x["delta"]))}</div></div>' for x in rows)
        lbl = "밈 템플릿 순위 변동 Top 5"
        if not rows:
            lbl = "밈 템플릿 · 상위 30 순위 변동 없음"
            ent = ", ".join(f"{x['name']} ({x['rank']}위)" for x in im["entered"][:3]) or "없음"
            exi = ", ".join(f"{x['name']} (어제 {x['prev_rank']}위)" for x in im["exited"][:3]) or "없음"
            body = (f'<div class="xr"><small>100개 기준 신규 진입</small>{esc(ent)}</div><div class="xr"><small>이탈</small>{esc(exi)}</div>'
                    + "".join(f'<div class="mv"><img src="{H.escape(x["url"], quote=True)}" alt=""><div><div class="nm">{esc(x["name"])}</div><div class="cap">캡션 {(x.get("captions") or 0):,}</div></div><div class="kpi">{x["rank"]}위</div></div>' for x in im["items"][:3]))
    else:
        lbl = "밈 템플릿 인기 Top 5 (비교 없음)"
        body = "".join(f'<div class="mv"><img src="{H.escape(x["url"], quote=True)}" alt=""><div><div class="nm">{esc(x["name"])}</div><div class="cap">캡션 {(x.get("captions") or 0):,}</div></div><div class="kpi">{x["rank"]}위</div></div>' for x in im["items"][:5])
    cross = rep["cross"][:3]
    xs = "".join(f'<div class="xr"><div class="tm">{esc(c["term"])} → <b>{esc(c["game"])}</b></div><small>{"Steam" if c["platform"] == "steam" else "itch.io"} · {esc(c["source"])}</small></div>' for c in cross) or '<p class="empty" style="font-size:30px;margin:14px 0">오늘은 겹치는 게임이 없습니다.</p>'
    more = f'<div class="xr"><small>외 {len(rep["cross"]) - 3}건 · 상세 보고서 참고</small></div>' if len(rep["cross"]) > 3 else ""
    return f'<p class="lbl">{esc(lbl)}</p>{body}<div class="sec"><p class="lbl">게임 ↔ 밈 교차</p>{xs}{more}</div>'


def to_cards(rep):
    eyebrow = f"미디어·밈 리포트 · {rep['round']}회차"
    pages = [(TITLE, _cover_body(rep)), ("밈 템플릿 · 게임 교차", _second_body(rep))]
    return [(f"{rep['date']}-{i}.png", _card(body, rep, i, len(pages), title, eyebrow)) for i, (title, body) in enumerate(pages, 1)]


# ====================================================================
# Discord 임베드
# ====================================================================

def build_embeds(rep, link, clip, limits):
    """clip(s, n) 과 limits(dict: title, desc, field_name, field, footer, total) 는 notify.py 의 것을 넘깁니다."""
    LT, LD, LFN, LF, LFT, LTOT = (limits[k] for k in ("title", "desc", "field_name", "field", "footer", "total"))
    embeds = []
    p = rep.get("pick")
    cover = {"title": clip(f"{TITLE} · {date_ko(rep['date'])} · {rep['round']}회차", LT), "color": COLOR}
    if link:
        cover["url"] = link
    lines = []
    if p:
        streak = f" · {p['streak']}일 연속" if p.get("streak", 1) > 1 else ""
        lines.append(f"**오늘의 트렌드 → [{_mdsafe(p['title'])}]({p['url']})**{streak}")
        if p.get("summary"):
            lines.append(_sum(p["summary"]))
        if p.get("platforms"):
            lines.append(" · ".join(p["platforms"]))
        if p.get("image"):
            cover["image"] = {"url": p["image"]}
    else:
        lines.append("최근 48시간 KYM 기사가 없습니다.")
    pc = " · ".join(f"{a} {n}건" for a, n in rep["platform_counts"]) or "플랫폼 단서 없음"
    lines.append(f"\n**플랫폼 집계** KYM {len(rep['kym'])}건 (신규 {rep['kym_new']}) · {pc}")
    others = [x for x in rep["kym"] if not p or x["url"] != p["url"]][:4]
    if others:
        lines.append("\n**다른 기사**\n" + "\n".join(f"• [{_mdsafe(x['title'])}]({x['url']})" + (f" · {' · '.join(x['platforms'])}" if x.get("platforms") else "") for x in others))
    cover["description"] = clip("\n".join(lines), LD)
    embeds.append(cover)

    fields = []
    for geo in ("KR", "US"):
        top = rep["trends"][geo][:5]
        val = "\n".join(f"**{x['rank']}.** [{_mdsafe(x['title'])}]({x['url']}) · {_fmt_traffic(x)}" + (f" · {x['days']}일 연속" if x.get("days", 1) > 1 else "") for x in top) or "수집 실패"
        fields.append({"name": clip(f"{geo} Top 5", LFN), "value": clip(val, LF), "inline": True})
    embeds.append({"title": "검색 급상승 · Google 트렌드", "color": COLOR, "fields": fields})

    im = rep["imgflip"]
    if im["compared"]:
        body = "\n".join(f"• **{_mdsafe(x['name'])}** {x['prev_rank']}→{x['rank']}위 {_arrow(x['delta'])}" for x in im["movers"][:5]) or "• 상위 30 안에서 순위 변동 없음"
        body += "\n신규 진입: " + (", ".join(_mdsafe(x["name"]) for x in im["entered"][:5]) or "없음")
        body += "\n이탈: " + (", ".join(_mdsafe(x["name"]) for x in im["exited"][:5]) or "없음")
    else:
        body = "비교 대상 없음 (회차 1)\n" + "\n".join(f"• **{x['rank']}.** {_mdsafe(x['name'])}" for x in im["items"][:5])
    embeds.append({"title": "밈 템플릿 순위 변동 · Imgflip", "color": COLOR, "description": clip(body, LD)})

    if rep["cross"]:
        body = "\n".join(f"• {_mdsafe(c['term'])} → [{_mdsafe(c['game'])}]({c['game_url']}) ({'Steam' if c['platform'] == 'steam' else 'itch'}) · {c['source']}" for c in rep["cross"][:8])
        embeds.append({"title": f"게임 ↔ 밈 교차 · {len(rep['cross'])}건", "color": 0x146C43, "description": clip(body, LD)})

    wf = []
    for proj, lbl in (("en", "위키 en"), ("ko", "위키 ko")):
        val = "\n".join(f"**{x['rank']}.** [{_mdsafe(x['title'])}]({x['url']}) · {x['views']:,}" for x in rep["wiki"][proj][:3]) or "수집 실패"
        wf.append({"name": clip(lbl, LFN), "value": clip(val, LF), "inline": True})
    rd = [f"• r/{r['sub']} [{_mdsafe(r['items'][0]['title'])}]({r['items'][0]['url']})" for r in rep["reddit"] if r["status"] == "ok" and r["items"]]
    fails = [f"r/{r['sub']}" for r in rep["reddit"] if r["status"] != "ok"]
    desc = "\n".join(rd) or "Reddit 수집 실패"
    if fails:
        desc += f"\n(실패: {', '.join(fails)})"
    if link:
        desc += f"\n\n**[📄 상세 보고서 열기]({link})**"
    embeds.append({"title": "세상의 관심사 · 커뮤니티 베스트", "color": COLOR, "fields": wf, "description": clip(desc, LD),
                   "footer": {"text": clip(rep["collect_line"], LFT)}})

    def elen(e):
        return len(e.get("title", "")) + len(e.get("description", "")) + len((e.get("footer") or {}).get("text", "")) + sum(len(f["name"]) + len(f["value"]) for f in e.get("fields", []))

    excess = sum(elen(e) for e in embeds) - LTOT
    for e in reversed(embeds):
        if excess <= 0:
            break
        d = e.get("description", "")
        if len(d) > 80:
            cut = min(len(d) - 80, excess)
            e["description"] = clip(d, len(d) - cut)
            excess -= cut
    return embeds
