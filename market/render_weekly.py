"""주간 리포트 HTML 과 캡슐 아트 보드 카드 HTML.

- to_html(data, boards, dates): reports/weekly/<date>.html. 일간 HTML 과 같은 CSS(render.CSS) 위에 표 스타일만 더합니다.
- board_cards(games, platform, dates): [(파일명, html)] 1080×1350 세로 카드 1~2장. 이미지는 data URI(수집 단계에서 받아 둔 것).
"""
import html as H
from datetime import datetime

from . import render
from .render import date_ko, esc

PER_CARD = {"steam": 18, "itch": 20}  # 3열×6행, 4열×5행
MAX_CARDS = 2

WEEKLY_CSS = """
.sum{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:22px 0 0}
.sum .tile dd{font-size:26px}
section{margin-top:40px}
section h2{font-family:var(--serif);font-size:26px;margin:0 0 6px}
.lead{color:var(--muted);font-size:14.5px;margin:0 0 14px;max-width:90ch}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--surface);box-shadow:var(--shadow)}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{padding:9px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle;white-space:nowrap}
th{font-family:var(--mono);font-size:11.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);background:var(--surface-2);position:sticky;top:0}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:0}
td.tag{font-weight:600}
td.tag small{display:block;font-weight:400;color:var(--faint);font-size:12px}
.bar{display:inline-block;height:8px;border-radius:4px;background:var(--rise);vertical-align:middle;margin-right:6px}
.bar.mid{background:var(--accent)}
.ex{display:flex;gap:6px;align-items:center}
.ex a{display:block;width:92px;aspect-ratio:231/87;border-radius:4px;background:hsl(var(--h,220) var(--ph-s) var(--ph-l));background-size:cover;background-position:center;flex:none}
.ex a span{position:absolute;left:-9999px}
.rk{color:var(--faint);font-family:var(--mono);font-size:12px}
.hot td.tag{color:var(--rise)}
.flag{font-size:11px;color:var(--warn);background:var(--warn-soft);border-radius:4px;padding:1px 6px;margin-left:6px;font-weight:500}
.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}
@media(max-width:860px){.two{grid-template-columns:1fr}}
.list{margin:0;padding:0;list-style:none}
.list li{display:grid;grid-template-columns:28px minmax(0,1fr) auto;gap:10px;align-items:baseline;padding:9px 0;border-bottom:1px solid var(--line)}
.list li:last-child{border:0}
.list b{font-size:16px}
.list .n{font-family:var(--mono);font-size:13px;color:var(--muted)}
.list .v{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums;color:var(--rise)}
.boards{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px}
.boards figure{margin:0;background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden;box-shadow:var(--shadow)}
.boards img{display:block;width:100%;height:auto}
.boards figcaption{padding:10px 14px;font-size:13.5px;color:var(--muted)}
.gl{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:8px 16px;margin:14px 0 0;padding:0;list-style:none;font-size:13.5px}
.gl li{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gl .m{color:var(--muted)}
.method{font-size:13.5px;color:var(--muted);line-height:1.7}
"""


def _pct_cell(v, cls="", max_v=100):
    w = max(2, round(min(100, 100 * v / max_v)) * 0.9)
    return f'<td class="num"><span class="bar {cls}" style="width:{w}px"></span>{v:.1f}%</td>'


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
    out = [f'<div class="tw"><table><thead><tr><th>#</th><th>태그</th><th class="num">1년 출시</th><th class="num">리뷰 {succ}+</th>'
           f'<th class="num">리뷰 {mid}+</th><th class="num">리뷰 10 미만</th><th class="num">중앙값</th><th class="num">틈 지수</th><th>대표 성공작 (리뷰 많은 순)</th></tr></thead><tbody>']
    for i, t in enumerate(rows, 1):
        flags = ""
        if t["truncated"]:
            flags += f'<span class="flag">최근 {t["window_days"]}일 표본</span>'
        if not t["ranked"]:
            flags += '<span class="flag">표본 부족</span>'
        niche = f"{t['niche']:.1f}" if t.get("niche") is not None else "—"
        med = f"{t['median']:,.0f}" if t["median"] == int(t["median"]) else f"{t['median']:,.1f}"
        out.append(f'<tr class="{"hot" if t["name"] in hot_names else ""}"><td class="rk">{i}</td><td class="tag">{esc(t["name"])}{flags}'
                   f'<small>{t["n_success"]}개 · {t["n_mid"]}개 · {t["n_low"]}개</small></td><td class="num">{t["n"]:,}</td>'
                   + _pct_cell(t["p_success"], "", max_p) + _pct_cell(t["p_mid"], "mid", max_p)
                   + f'<td class="num">{t["p_low"]:.1f}%</td><td class="num">{med}</td><td class="num">{niche}</td><td>{_ex_html(t["top"])}</td></tr>')
    out.append("</tbody></table></div>")
    return "".join(out)


def rank_list_html(items, value_key, fmt, note):
    lis = "".join(f'<li><span class="n">{i}</span><div><b>{esc(t["name"])}</b><div class="n">{esc(note(t))}</div></div><span class="v">{fmt(t[value_key])}</span></li>'
                  for i, t in enumerate(items, 1))
    return f'<ul class="list">{lis}</ul>' if lis else '<p class="empty">표본이 충분한 태그가 없습니다.</p>'


def to_html(data, top, niche, boards, dates, cfg):
    """data: collect_tags 결과. boards: {platform: {"games": [...], "pngs": [파일명]}}."""
    w = cfg["weekly"]
    d0, d1 = dates[0], dates[-1]
    title = f"주간 분석 · {date_ko(d0)} ~ {date_ko(d1)}"
    ranked = [t for t in data["tags"] if t["ranked"]]
    all_n = sum(t["n"] for t in data["tags"])
    all_mid = sum(t["n_mid"] for t in data["tags"])
    tiles = [("태그", f"{len(data['tags'])}개"), ("수집 게임(중복 제거)", f"{data['games_total']:,}개"),
             (f"전체 {data['mid_reviews']}+ 비율", f"{100 * all_mid / all_n:.1f}%" if all_n else "—"),
             ("요청 수", f"{data['requests']:,}회"), ("기간", f"{data['since']} ~ {data['until']}")]
    tiles_html = "".join(f'<dl class="tile"><dt>{esc(k)}</dt><dd>{esc(v)}</dd></dl>' for k, v in tiles)
    top_html = rank_list_html(top, "p_success", lambda v: f"{v:.1f}%", lambda t: f"1년 출시 {t['n']:,}개 · {data['mid_reviews']}+ {t['p_mid']:.1f}% · 중앙값 {t['median']:,.0f}")
    niche_html = rank_list_html(niche, "niche", lambda v: f"{v:.1f}", lambda t: f"1년 출시 {t['n']:,}개 · {data['mid_reviews']}+ {t['p_mid']:.1f}% · {data['success_reviews']}+ {t['p_success']:.1f}%")
    hot = {t["name"] for t in niche}
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
    toc = '<a href="#s1"><b>1</b>태그별 성공률</a><a href="#s2"><b>2</b>캡슐 아트 보드</a><a href="#s3"><b>3</b>계산 방법</a>'
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap">
<style>{render.CSS}{WEEKLY_CSS}</style></head>
<body class="weekly"><div class="wrap">
<header><p class="eyebrow">주간 리포트 · 무엇을 만들지 정하는 데 쓰는 두 가지</p><h1>{esc(title)}</h1>
<ul class="basis"><li>최근 {data['window_days']}일 안에 출시된 Indie 태그 게임을 태그별로 세고 리뷰 수로 성공률을 봅니다</li><li>리뷰 {data['success_reviews']}+ ≈ 판매 1만 장(Boxleiter 배수 20~30 기준)</li><li>캡슐 보드는 최근 7일 일간 리포트에 오른 게임의 스토어 이미지입니다</li></ul>
<div class="sum">{tiles_html}</div></header>
<nav class="toc">{toc}</nav>
<section id="s1"><h2>1. 태그별 성공률 (Steam · 최근 1년 출시작)</h2>
<p class="lead">성공률이 높으면서 1년 출시 수가 적은 태그가 "공급이 적은 틈"입니다. 표는 리뷰 {data['success_reviews']}+ 비율 내림차순이고, 초록 줄은 틈 후보입니다. 표본 {data['min_games']}개 미만 태그는 순위에서 뺍니다.</p>
<div class="two"><div class="card side"><h3>성공률 상위 5 · 리뷰 {data['success_reviews']}+ 비율</h3>{top_html}</div>
<div class="card side"><h3>틈 후보 3 · 틈 지수</h3>{niche_html}</div></div>
<div style="height:18px"></div>{tag_table_html(data, hot)}</section>
<section id="s2"><h2>2. 캡슐 아트 보드 (Steam + itch.io · 최근 7일 급상승 게임)</h2>
<p class="lead">스토어 캡슐 디자인 참고용입니다. 일간 리포트의 선정 게임 · 큰 폭 변화 · 급상승 Top 3 에 오른 게임을 등장 횟수 순으로 모았습니다. 이미지 아래 한 줄은 그 주의 핵심 수치입니다.</p>
{boards_html}{"".join(lists)}</section>
<section id="s3"><h2>3. 계산 방법</h2><p class="method">
· 모집단: Steam 검색(출시일 내림차순, Indie 태그 + 해당 태그, 게임만)을 {data['since']} 이전 출시작이 나올 때까지 넘깁니다. 태그당 최대 {w.get('max_pages_per_tag', 24)}페이지(100개씩)이며, 그 안에 1년을 다 못 받은 태그는 "최근 N일 표본"으로 표시합니다(출시 수는 실제보다 적게, 성공률은 리뷰가 덜 쌓여 낮게 나옵니다).<br>
· 리뷰 수는 검색 결과의 "n user reviews"(전 언어 합계)이고, 리뷰가 없는 게임은 0으로 셉니다.<br>
· 틈 지수 = (리뷰 {data['mid_reviews']}+ 비율 %) × log10({data['niche_base']:,} ÷ 1년 출시 수). 표본 {data['min_games']}개 이상인 태그만 계산합니다. 자세한 정의는 rules.md §11.<br>
· 캡슐 보드의 Steam 이미지는 스토어 header(460×215), itch 는 목록 썸네일(315×250)입니다.
</p></section>
<footer>생성 {data['generated']} KST · 요청 {data['requests']:,}회 · 모든 수치는 비공식 검색 결과 기반 추정치입니다.</footer>
</div></body></html>"""


# ---------- 캡슐 아트 보드 카드 (1080×1350) ----------

BOARD_CSS = """
*{box-sizing:border-box}
html,body{margin:0;width:1080px;height:1350px;overflow:hidden}
body{background:#0F1217;color:#E8EBF1;font-family:"IBM Plex Sans KR","Apple SD Gothic Neo","Noto Sans CJK KR","Noto Sans KR","Malgun Gothic",sans-serif;-webkit-font-smoothing:antialiased;word-break:keep-all}
.card{width:1080px;height:1350px;padding:20px 20px 16px;display:flex;flex-direction:column}
.head{display:flex;justify-content:space-between;align-items:baseline;height:56px;flex:none}
.head h1{font-size:30px;margin:0;font-weight:700;letter-spacing:-.01em}
.head h1 span{color:#9AA6F5;font-weight:600;margin-right:12px;font-size:22px;letter-spacing:.08em;text-transform:uppercase}
.head .r{font-size:20px;color:#A6AEBC;font-variant-numeric:tabular-nums}
.grid{display:grid;gap:10px;flex:1;min-height:0;align-content:start}
body.steam .grid{grid-template-columns:repeat(3,340px);grid-auto-rows:199px}
body.itch .grid{grid-template-columns:repeat(4,252px);grid-auto-rows:238px}
.g{display:flex;flex-direction:column;min-width:0}
.im{width:100%;background:hsl(var(--h,220) 36% 36%);background-size:cover;background-position:center;background-repeat:no-repeat;border-radius:6px;flex:none;position:relative;overflow:hidden}
body.steam .im{height:159px}
body.itch .im{height:198px}
.im b{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:64px;color:rgba(255,255,255,.55);font-family:Georgia,serif}
.cap{height:40px;padding:5px 2px 0;display:flex;flex-direction:column;justify-content:flex-start;min-width:0}
.nm{font-size:17px;font-weight:600;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mt{font-size:14px;color:#A6AEBC;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}
.mt .up{color:#63D692}.mt .dn{color:#F7928A}
.foot{height:24px;flex:none;display:flex;justify-content:space-between;font-size:15px;color:#737C8D;margin-top:6px}
"""


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


def board_cards(games, platform, dates):
    """[(파일명, html)] · 플랫폼당 최대 MAX_CARDS 장. 파일명 <date>-board-<platform>.png, 두 번째는 -2."""
    per = PER_CARD[platform]
    ko = "Steam" if platform == "steam" else "itch.io"
    pages = [games[i:i + per] for i in range(0, min(len(games), per * MAX_CARDS), per)]
    out = []
    period = f"{date_ko(dates[0])} ~ {date_ko(dates[-1])}"
    for i, chunk in enumerate(pages, 1):
        tiles = "".join(_tile(g) for g in chunk)
        fname = f"{dates[-1]}-board-{platform}.png" if i == 1 else f"{dates[-1]}-board-{platform}-{i}.png"
        out.append((fname, f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>{esc(ko)} 캡슐 보드</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;600;700&display=swap">
<style>{BOARD_CSS}</style></head>
<body class="{esc(platform)}"><div class="card">
<div class="head"><h1><span>캡슐 보드</span>{esc(ko)} · 이번 주 급상승 {len(games)}개</h1><div class="r">{esc(period)} · {i} / {len(pages)}</div></div>
<div class="grid">{tiles}</div>
<div class="foot"><span>일간 리포트 선정 게임 · 큰 폭 변화 · 급상승 Top 3 에 오른 게임 (등장 횟수 순) · 스토어 캡슐 디자인 참고용</span><span>indie-trending</span></div>
</div></body></html>"""))
    return out
