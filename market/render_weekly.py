"""주간 리포트 HTML · 틈새 지도 카드 · 캡슐 아트 보드 카드 (design/tokens.json + market/ui.py + market/charts.py).

- to_html(data, top, niche, boards, dates, cfg): reports/weekly/<date>.html. 일간 페이지 CSS(render.daily_css) 위에 주간 규칙 몇 줄만.
- niche_card(data, top, niche, dates, link, i, n): 틈새 지도 1장 (가로 = 1년 출시 수 로그, 세로 = 성공률, 점 크기 = 중앙값 리뷰).
- board_cards(games, platform, dates, start, n_total, link): 캡슐 보드 1~2장 (토큰 틀).
"""
import html as H
from statistics import median

from . import charts, headline, render, ui
from .render import date_ko, esc

PER_CARD = {"steam": 18, "itch": 20}  # 3열×6행, 4열×5행
MAX_CARDS = 2
TAG = "Indie Trending · Weekly"

WEEKLY_CSS = """
.sum{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));border:var(--bw) solid var(--line);margin:var(--sp-lg) 0 0}
.sum div{padding:var(--sp-md);border-right:var(--bw) solid var(--line);min-width:0}.sum div:last-child{border-right:0}
.sum dt{font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink-2);margin:0}
.sum dd{margin:0;font:var(--t-data-lg-w) var(--t-data-lg) var(--font-mono);letter-spacing:var(--t-data-lg-ls);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.two{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:var(--gutter);align-items:start}
@media(max-width:1023px){.two{grid-template-columns:1fr}}
.list{margin:0;padding:0;list-style:none}
.list li{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:var(--sp-md);align-items:center;padding:var(--sp-sm) 0;border-top:var(--bw) solid var(--line)}
.list li:first-child{border-top:0;padding-top:0}
.list b{font:var(--t-headline-md-w) var(--t-headline-md) var(--font-display);letter-spacing:var(--t-headline-md-ls)}
.list .n{font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);letter-spacing:var(--t-data-md-ls);color:var(--ink-2)}
.list .v{font:700 var(--t-data-lg) var(--font-mono);letter-spacing:var(--t-data-lg-ls);color:var(--rise)}
.ex{display:flex;gap:var(--sp-xs);align-items:center}
.ex a{display:block;width:80px;aspect-ratio:231/87;border:var(--bw) solid var(--line);background:hsl(var(--h,220) var(--ph-s) var(--ph-l));background-size:cover;background-position:center;flex:none}
.ex a span{position:absolute;left:-9999px}
td.tag{font-family:var(--font-body);font-weight:600;white-space:normal;min-width:160px}
td.tag small{display:block;font:var(--t-body-sm-w) var(--t-body-sm) var(--font-mono);color:var(--ink-3)}
.bar{display:inline-block;height:8px;background:var(--line-strong);vertical-align:middle;margin-right:6px}
.bar.hot{background:var(--rise)}
tr.hot td.tag{color:var(--rise)}
.flag{font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);color:var(--warn);background:var(--warn-soft);padding:1px 6px;margin-left:6px}
.boards{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:var(--gutter)}
.boards figure{margin:0;background:var(--surface);border:var(--bw) solid var(--line);overflow:hidden}
.boards img{display:block;width:100%;height:auto}
.boards figcaption{padding:var(--sp-sm) var(--sp-md);font:var(--t-body-sm-w) var(--t-body-sm) var(--font-body);color:var(--ink-2)}
.gl{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:var(--sp-xs) var(--sp-md);margin:var(--sp-md) 0 0;padding:0;list-style:none;font:var(--t-body-md-w) var(--t-body-md) var(--font-body)}
.gl li{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gl .m{color:var(--ink-2);font-family:var(--font-mono);font-size:12px}
.method{font:var(--t-body-md-w) var(--t-body-md) var(--font-body);color:var(--ink-2);line-height:1.7}
h3{margin:var(--sp-lg) 0 var(--sp-xs);font:var(--t-headline-md-w) var(--t-headline-md) var(--font-display)}
"""


# ---------- 틈새 지도 데이터 ----------

def niche_points(data, niche, n_label=12):
    """산점도 점 [(이름, 출시 수, 성공률, 중앙값 리뷰, kind)] 와 사분면 경계 {x, y}. kind: hi = 틈새 후보 3, label = 눈에 띄는 9개, '' = 나머지."""
    ranked = [t for t in data["tags"] if t.get("ranked")]
    if not ranked:
        return [], None
    hot = {t["name"] for t in niche}
    by_n = sorted(ranked, key=lambda t: -t["n"])[:4]
    by_p = sorted(ranked, key=lambda t: -t["p_success"])[:6]
    by_mid = sorted(ranked, key=lambda t: -t["p_mid"])[:3]
    labeled = {t["name"] for t in by_n + by_p + by_mid} - hot
    labeled = set(list(labeled)[: max(n_label - len(hot), 0)])
    pts = []
    for t in sorted(ranked, key=lambda t: t["n"]):
        kind = "hi" if t["name"] in hot else "label" if t["name"] in labeled else ""
        pts.append((t["name"], t["n"], t["p_success"], max(t.get("median") or 0, 0), kind))
    quad = {"x": median(t["n"] for t in ranked), "y": median(t["p_success"] for t in ranked), "label": "틈새 · 출시 적고 성공률 높음"}
    return pts, quad


def niche_svg(data, niche, width, height, scale):
    pts, quad = niche_points(data, niche)
    return charts.scatter(pts, width=width, height=height, scale=scale, x_log=True, x_kind="num", y_kind="pct",
                          x_label=f"최근 {data['window_days']}일 출시 수 (로그)", y_label=f"성공률 · 리뷰 {data['success_reviews']}+ 비율",
                          quadrant=quad, title="틈새 지도", size_range=(5, 20) if scale == "card" else (4, 14), label_chars=18)


def _example(t):
    return (t.get("top") or [{}])[0].get("name") or ""


def niche_lines(data, niche):
    tags = {t["name"]: t for t in data["tags"]}
    out = []
    for i, t in enumerate(niche, 1):
        full = tags.get(t["name"], t)
        ex = _example(full)
        out.append(f'<p><b>{i} {esc(t["name"])}</b> · 출시 {t["n"]:,}개 · 성공률 {t["p_success"]:.1f}% · 틈 지수 {t["niche"]:.1f}' + (f" · 예시 {esc(ex)}" if ex else "") + "</p>")
    return out


# ---------- HTML ----------

def _pct_cell(v, hot=False, max_v=100):
    w = max(2, round(min(100, 100 * v / max_v)) * 0.9)
    return f'<td class="num"><span class="bar{" hot" if hot else ""}" style="width:{w}px"></span>{v:.1f}%</td>'


def _ex_html(top):
    out = []
    for g in top:
        style = f"background-image:url({H.escape(g['img'], quote=True)});" if g.get("img") else f"--h:{render.hue(g['name'])};"
        out.append(f'<a href="{H.escape(g["url"], quote=True)}" target="_blank" rel="noopener" style="{style}" title="{H.escape(g["name"] + " · 리뷰 " + f"{g['reviews']:,}", quote=True)}"><span>{esc(g["name"])}</span></a>')
    return f'<div class="ex">{"".join(out)}</div>'


def tag_table_html(data, hot_names):
    succ, mid = data["success_reviews"], data["mid_reviews"]
    rows = sorted(data["tags"], key=lambda t: (-t["p_success"], -t["p_mid"], -t["n"]))
    max_p = max((t["p_mid"] for t in rows), default=100) or 100
    out = [f'<div class="tbl solo"><table><thead><tr><th class="num">#</th><th>태그</th><th class="num">1년 출시</th><th class="num">리뷰 {succ}+</th>'
           f'<th class="num">리뷰 {mid}+</th><th class="num">리뷰 10 미만</th><th class="num">중앙값</th><th class="num">틈 지수</th><th>대표 성공작 (리뷰 많은 순)</th></tr></thead><tbody>']
    for i, t in enumerate(rows, 1):
        flags = ""
        if t["truncated"]:
            flags += f'<span class="flag">최근 {t["window_days"]}일 표본</span>'
        if not t["ranked"]:
            flags += '<span class="flag">표본 부족</span>'
        niche = f"{t['niche']:.1f}" if t.get("niche") is not None else "—"
        med = f"{t['median']:,.0f}" if t["median"] == int(t["median"]) else f"{t['median']:,.1f}"
        hot = t["name"] in hot_names
        out.append(f'<tr class="{"hot" if hot else ""}"><td class="num">{i}</td><td class="tag">{esc(t["name"])}{flags}'
                   f'<small>{t["n_success"]}개 · {t["n_mid"]}개 · {t["n_low"]}개</small></td><td class="num">{t["n"]:,}</td>'
                   + _pct_cell(t["p_success"], hot, max_p) + _pct_cell(t["p_mid"], False, max_p)
                   + f'<td class="num">{t["p_low"]:.1f}%</td><td class="num">{med}</td><td class="num">{niche}</td><td>{_ex_html(t["top"])}</td></tr>')
    out.append("</tbody></table></div>")
    return "".join(out)


def rank_list_html(items, value_key, fmt, note):
    lis = "".join(f'<li><span class="rank{" top" if i <= 3 else ""}">{i:02d}</span><div><b>{esc(t["name"])}</b><div class="n">{esc(note(t))}</div></div><span class="v">{fmt(t[value_key])}</span></li>'
                  for i, t in enumerate(items, 1))
    return f'<ul class="list">{lis}</ul>' if lis else '<p class="empty">표본이 충분한 태그가 없습니다.</p>'


def to_html(data, top, niche, boards, dates, cfg, niche_png=None):
    w = cfg["weekly"]
    d0, d1 = dates[0], dates[-1]
    title = f"주간 분석 · {date_ko(d0)} ~ {date_ko(d1)}"
    all_n = sum(t["n"] for t in data["tags"])
    all_mid = sum(t["n_mid"] for t in data["tags"])
    tiles = [("태그", f"{len(data['tags'])}개"), ("수집 게임", f"{data['games_total']:,}개"),
             (f"전체 {data['mid_reviews']}+ 비율", f"{100 * all_mid / all_n:.1f}%" if all_n else "—"),
             ("요청 수", f"{data['requests']:,}회"), ("기간", f"{data['since']} ~ {data['until']}")]
    tiles_html = "".join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in tiles)
    top_html = rank_list_html(top, "p_success", lambda v: f"{v:.1f}%", lambda t: f"1년 출시 {t['n']:,}개 · {data['mid_reviews']}+ {t['p_mid']:.1f}% · 중앙값 {t['median']:,.0f}")
    niche_html = rank_list_html(niche, "niche", lambda v: f"{v:.1f}", lambda t: f"1년 출시 {t['n']:,}개 · {data['mid_reviews']}+ {t['p_mid']:.1f}% · {data['success_reviews']}+ {t['p_success']:.1f}%")
    hot = {t["name"] for t in niche}
    hl = headline.to_html(headline.weekly_niche(niche[0])) if niche else esc("표본이 충분한 태그가 없습니다")
    figs, lists = [], []
    for platform, ko in (("steam", "Steam"), ("itch", "itch.io")):
        b = boards.get(platform) or {}
        for i, png in enumerate(b.get("pngs") or [], 1):
            figs.append(f'<figure><img src="cards/{esc(png)}" alt="{ko} 캡슐 보드 {i}" loading="lazy"><figcaption>{ko} 캡슐 보드 {i} · {len(b.get("games") or [])}개 중 {min(len(b.get("games") or []), PER_CARD[platform] * i)}개까지</figcaption></figure>')
        gl = "".join(f'<li><a href="{H.escape(g["url"], quote=True)}" target="_blank" rel="noopener">{esc(g["name"])}</a> <span class="m">{esc(g["metric"])} · {g["days"]}일</span></li>'
                     for g in (b.get("games") or []))
        if gl:
            lists.append(f'<h3>{ko} · {len(b["games"])}개</h3><ul class="gl">{gl}</ul>')
    boards_html = f'<div class="boards">{"".join(figs)}</div>' if figs else '<p class="empty">보드 이미지가 없습니다 (Chrome 을 찾지 못했거나 게임이 없음).</p>'
    toc = '<a href="#s1"><b>01</b>틈새 지도</a><a href="#s2"><b>02</b>태그별 성공률</a><a href="#s3"><b>03</b>캡슐 아트 보드</a><a href="#s4"><b>04</b>계산 방법</a>'
    scatter = niche_svg(data, niche, 1112, 520, "web")
    return f"""<!doctype html>
<html lang="ko" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(title)}</title>
{ui.font_links()}
<style>{render.daily_css("steam")}{WEEKLY_CSS}</style></head>
<body class="weekly"><div class="wrap">
<div class="appbar"><div style="display:flex;align-items:center;gap:var(--sp-lg);height:100%"><span class="brand">Indie Trending</span><nav><a href="../steam/{d1}.html">Steam</a><a href="../itch/{d1}.html">itch.io</a><a class="on" href="#">Weekly</a></nav></div><span class="when">{esc(date_ko(d0))} ~ {esc(date_ko(d1))}</span></div>
<header class="rh"><div class="hrow"><div class="l"><span class="ptag">{esc(TAG)}</span><span class="seclabel">Weekly Report</span></div><div class="r"><span class="when">{esc(d0)} ~ {esc(d1)}</span></div></div>
<h1>{hl}</h1>
<ul class="basis"><li>최근 {data['window_days']}일 안에 출시된 Indie 태그 게임을 태그별로 세고 리뷰 수로 성공률을 봅니다</li><li>리뷰 {data['success_reviews']}+ ≈ 판매 1만 장(Boxleiter 배수 20~30 기준)</li><li>캡슐 보드는 최근 7일 일간 리포트에 오른 게임의 스토어 이미지입니다</li></ul>
<dl class="sum">{tiles_html}</dl></header>
<nav class="toc">{toc}</nav>
<section id="s1"><h2><span class="no">01</span>틈새 지도 · 출시 수 × 성공률</h2>
<p class="sbasis">가로축은 최근 1년 출시 수(로그), 세로축은 리뷰 {data['success_reviews']}+ 비율, 점 크기는 중앙값 리뷰 수입니다. 왼쪽 위(출시 적고 성공률 높음)가 틈새이고 초록 점이 틈새 후보 3개입니다. 표본 {data['min_games']}개 미만 태그는 뺍니다.</p>
<div class="two"><div class="panel" style="padding:var(--sp-lg)"><div class="chartbox">{scatter}</div><div class="lines" style="margin-top:var(--sp-md);display:flex;flex-direction:column;gap:4px;font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);color:var(--ink-2)">{"".join(niche_lines(data, niche))}</div></div>
<div style="display:flex;flex-direction:column;gap:var(--gutter)"><div class="panel side"><p class="seclabel">틈 후보 3 · 틈 지수</p>{niche_html}</div><div class="panel side"><p class="seclabel">성공률 상위 5 · 리뷰 {data['success_reviews']}+ 비율</p>{top_html}</div></div></div></section>
<section id="s2"><h2><span class="no">02</span>태그별 성공률 (Steam · 최근 1년 출시작)</h2>
<p class="sbasis">표는 리뷰 {data['success_reviews']}+ 비율 내림차순이고, 초록 줄은 틈 후보입니다. 표본 {data['min_games']}개 미만 태그는 순위에서 뺍니다.</p>
{tag_table_html(data, hot)}</section>
<section id="s3"><h2><span class="no">03</span>캡슐 아트 보드 (Steam + itch.io · 최근 7일 급상승 게임)</h2>
<p class="sbasis">스토어 캡슐 디자인 참고용입니다. 일간 리포트의 선정 게임 · 큰 폭 변화 · 급상승 Top 3 에 오른 게임을 등장 횟수 순으로 모았습니다.</p>
{boards_html}{"".join(lists)}</section>
<section id="s4"><h2><span class="no">04</span>계산 방법</h2><p class="method">
· 모집단: Steam 검색(출시일 내림차순, Indie 태그 + 해당 태그, 게임만)을 {data['since']} 이전 출시작이 나올 때까지 넘깁니다. 태그당 최대 {w.get('max_pages_per_tag', 24)}페이지(100개씩)이며, 그 안에 1년을 다 못 받은 태그는 "최근 N일 표본"으로 표시합니다.<br>
· 리뷰 수는 검색 결과의 "n user reviews"(전 언어 합계)이고, 리뷰가 없는 게임은 0으로 셉니다.<br>
· 틈 지수 = (리뷰 {data['mid_reviews']}+ 비율 %) × log10({data['niche_base']:,} ÷ 1년 출시 수). 표본 {data['min_games']}개 이상인 태그만 계산합니다. 자세한 정의는 rules.md §11.<br>
· 캡슐 보드의 Steam 이미지는 스토어 header(460×215), itch 는 목록 썸네일(315×250)입니다.
</p></section>
<footer class="pf">생성 {data['generated']} KST · 요청 {data['requests']:,}회 · 모든 수치는 비공식 검색 결과 기반 추정치입니다.</footer>
</div></body></html>"""


# ---------- 카드 ----------

CARD_CSS = """
.grid{display:grid;gap:8px;flex:1 1 auto;min-height:0}
body.steam .grid{grid-template-columns:repeat(3,1fr);grid-template-rows:repeat(6,minmax(0,1fr))}
body.itch .grid{grid-template-columns:repeat(4,1fr);grid-template-rows:repeat(5,minmax(0,1fr))}
.g{display:flex;flex-direction:column;min-width:0;min-height:0;background:var(--surface);border:var(--bw) solid var(--line)}
.im{width:100%;flex:1 1 auto;min-height:0;background:hsl(var(--h,220) var(--ph-s) var(--ph-l));background-size:cover;background-position:center;background-repeat:no-repeat;position:relative;overflow:hidden;border-bottom:var(--bw) solid var(--line)}
.im b{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font:700 56px var(--font-display);color:var(--ph-ink)}
.cap{padding:5px 8px 6px;min-width:0;flex:none}
.nm{font:var(--t-body-md-w) var(--t-body-md) var(--font-body);font-weight:600;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--ink)}
.mt{font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px;text-transform:none}
.mt .up{color:var(--rise)}.mt .dn{color:var(--fall)}
"""


def _when(dates):
    return f"{date_ko(dates[0])} ~ {date_ko(dates[-1])}"


def niche_card(data, top, niche, dates, link, i=1, n=1):
    """틈새 지도 카드 HTML."""
    w = ui.tokens()["카드"]["폭"] - 2 * ui.tokens()["간격"]["카드_여백"] - 48
    hl = headline.to_html(headline.weekly_niche(niche[0])) if niche else "표본이 충분한 태그가 없습니다"
    body = (f'<div class="cardtitle"><div class="kick"><span class="lchip pos">NICHE MAP</span><span class="seclabel">최근 {data["window_days"]}일 Indie 출시작 · 태그 {len(data["tags"])}개</span></div>'
            f'<h1 class="hl">{hl}</h1></div>'
            f'<div class="chartp"><div class="ph"><p class="seclabel strong">출시 수 × 성공률 (리뷰 {data["success_reviews"]}+ 비율)</p><p class="seclabel">점 크기 = 중앙값 리뷰 수 · 초록 = 틈새 후보</p></div>'
            f'<div class="body">{niche_svg(data, niche, w, 700, "card")}</div></div>'
            f'<div class="lines">{"".join(niche_lines(data, niche))}</div>')
    return render.card_page("steam", TAG, "Weekly Report", _when(dates), None, body, i, n, link, fallback_see=f"주간 분석 · {_when(dates)}", title="주간 틈새 지도")


def _tile(g):
    data = g.get("data")
    style = f"background-image:url({data});" if data else f"--h:{render.hue(g['name'])};"
    if g.get("thumb_bg") and not data:
        style = f"background-color:{H.escape(g['thumb_bg'], quote=True)};"
    initial = "" if data else f"<b>{esc((g['name'] or '?').strip()[:1].upper())}</b>"
    metric = g.get("metric") or ""
    cls = "up" if "▲" in metric or "+" in metric else ("dn" if "▼" in metric or "−" in metric else "")
    days = f" · {g['days']}일" if g.get("days", 1) > 1 else ""
    return (f'<div class="g"><div class="im" style="{style}">{initial}</div><div class="cap"><div class="nm">{esc(g["name"])}</div>'
            f'<div class="mt"><span class="{cls}">{esc(metric)}</span>{esc(days)}</div></div></div>')


def board_pages(games, platform):
    per = PER_CARD[platform]
    return [games[i:i + per] for i in range(0, min(len(games), per * MAX_CARDS), per)]


def board_cards(games, platform, dates, link=None, start=2, n_total=None):
    """[(파일명, html)] · 플랫폼당 최대 MAX_CARDS 장. 파일명 <date>-board-<platform>.png, 두 번째는 -2. 페이지 번호는 start 부터."""
    ko = "Steam" if platform == "steam" else "itch.io"
    pages = board_pages(games, platform)
    n_total = n_total or (start - 1 + len(pages))
    out = []
    for i, chunk in enumerate(pages, 1):
        tiles = "".join(_tile(g) for g in chunk)
        fname = f"{dates[-1]}-board-{platform}.png" if i == 1 else f"{dates[-1]}-board-{platform}-{i}.png"
        body = (f'<div class="cardtitle"><div class="kick"><span class="lchip pos">CAPSULE BOARD</span><span class="seclabel">{esc(ko)} · 이번 주 급상승 {len(games)}개 · {i}/{len(pages)}</span></div>'
                f'<h2>{esc(ko)} 캡슐 아트 보드</h2></div><div class="grid">{tiles}</div>')
        html = render.card_page("steam" if platform == "steam" else "itch", TAG, "Weekly Report", _when(dates), None, body, start + i - 1, n_total, link,
                                fallback_see=f"주간 분석 · {_when(dates)}", extra_css=CARD_CSS, title=f"{ko} 캡슐 보드")
        out.append((fname, html))
    return out
