"""리포트 dict → Discord 본문(markdown) 과 HTML."""
import html as H
import re
from datetime import datetime

WEEK = "월화수목금토일"
LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def date_ko(date):
    d = datetime.strptime(date, "%Y-%m-%d")
    return f"{d.month}월 {d.day}일 ({WEEK[d.weekday()]})"


# ---------- Discord ----------

def to_md(rep):
    L = [f"**{rep['platform_ko']} 트렌딩 · {date_ko(rep['date'])} · {rep['round']}회차**"]
    p = rep.get("pick")
    if p:
        links = " · ".join(f"[{t}]({u})" for t, u in p["links"])
        L.append(f"오늘의 선정 게임: **[{p['name']}]({p['url']})**" + (f" · {p['streak']}일 연속" if p["streak"] > 1 else "") + f"\n{links}"
                 + (f"\n{p['sub']}" if p.get("sub") else "") + f"\n{p['line']}" + (f"\n`{' · '.join(p['badges'])}`" if p["badges"] else ""))
    L.append("**큰 폭 변화**\n" + "\n".join(f"• {h}" for h in rep["headline"]) if rep["headline"] else "**큰 폭 변화**\n• 없음")
    L.append("**특이사항**\n" + "\n".join(f"• {n}" for n in rep["notes"]) if rep["notes"] else "**특이사항**\n• 없음")
    L.append(f"-# {rep['collect_line']}")
    return "\n\n".join(L)


# ---------- HTML ----------

CSS = """
:root{--ground:#F5F6F9;--surface:#FFFFFF;--surface-2:#FAFBFC;--ink:#14161C;--muted:#5A6270;--faint:#8A93A3;--line:#DFE3EA;--line-strong:#C4CBD6;--accent:#33409E;--accent-soft:#ECEEF9;--rise:#146C43;--rise-soft:#E7F3EC;--fall:#B3261E;--fall-soft:#FBEBEA;--warn:#8A6100;--warn-soft:#FBF3E0;
--serif:"Gowun Batang",'Nanum Myeongjo',Georgia,serif;--sans:"IBM Plex Sans KR",-apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;--mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--ground:#0E1116;--surface:#161A21;--surface-2:#1B2028;--ink:#E7EAF0;--muted:#9AA2B1;--faint:#6F7889;--line:#262C37;--line-strong:#38414F;--accent:#94A0F2;--accent-soft:#1B2044;--rise:#5FD48B;--rise-soft:#12291D;--fall:#F58A82;--fall-soft:#2C1614;--warn:#DDB44F;--warn-soft:#2A2110}}
:root[data-theme="dark"]{--ground:#0E1116;--surface:#161A21;--surface-2:#1B2028;--ink:#E7EAF0;--muted:#9AA2B1;--faint:#6F7889;--line:#262C37;--line-strong:#38414F;--accent:#94A0F2;--accent-soft:#1B2044;--rise:#5FD48B;--rise-soft:#12291D;--fall:#F58A82;--fall-soft:#2C1614;--warn:#DDB44F;--warn-soft:#2A2110}
*{box-sizing:border-box}body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.72;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:0 16px 80px}
header{padding:48px 0 24px;border-bottom:2px solid var(--ink)}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--accent);margin:0 0 12px}
h1{font-family:var(--serif);font-weight:700;font-size:clamp(28px,4.6vw,44px);line-height:1.15;margin:0 0 12px;letter-spacing:-.01em}
.basis{margin:0;color:var(--muted);font-size:14px;max-width:80ch}
.status{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:1px;background:var(--line);border:1px solid var(--line);margin:24px 0 0}
.status div{background:var(--surface);padding:12px 14px}.status dt{font-family:var(--mono);font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin:0 0 4px}.status dd{margin:0;font-size:14px;font-weight:500;font-variant-numeric:tabular-nums}
.top{display:grid;grid-template-columns:1.2fr 1fr;gap:16px;margin-top:28px}@media(max-width:800px){.top{grid-template-columns:1fr}}
.card{background:var(--surface);border:1px solid var(--line);padding:18px 20px}
.card h3{margin:0 0 8px;font-family:var(--mono);font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--faint)}
.pick .name{font-family:var(--serif);font-size:24px;line-height:1.25;margin:0 0 4px}.pick .sub{color:var(--muted);font-size:13.5px}.pick .links{font-size:13px;margin:6px 0}
.badge{display:inline-block;font-family:var(--mono);font-size:10.5px;padding:1px 7px;border:1px solid var(--line-strong);border-radius:3px;margin-right:4px;color:var(--muted);vertical-align:middle}
.badge.new{color:var(--rise);border-color:var(--rise);background:var(--rise-soft)}.badge.excl{color:var(--fall);border-color:var(--fall);background:var(--fall-soft)}.badge.disc{color:var(--warn);border-color:var(--warn);background:var(--warn-soft)}
ul.bul{margin:0;padding-left:18px}ul.bul li{margin:4px 0}
section{margin-top:52px}h2{font-family:var(--serif);font-weight:700;font-size:24px;line-height:1.3;margin:0 0 6px}h2 .no{font-family:var(--mono);font-size:13px;color:var(--accent);margin-right:10px;vertical-align:middle}
.sbasis{color:var(--muted);font-size:13.5px;margin:0 0 16px;max-width:90ch}
.blocks{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}
.block h4{margin:0 0 10px;font-size:13.5px;color:var(--accent)}.block ol{margin:0;padding-left:20px}.block li{margin:0 0 10px;font-size:14px}.block .nm{font-weight:600}.block .ln{color:var(--muted);font-size:13px;display:block}.block .sb{color:var(--faint);font-size:12.5px;display:block}
.empty{color:var(--faint);font-size:13.5px}
table{border-collapse:collapse;width:100%;font-size:13px;margin:10px 0 18px;background:var(--surface)}th,td{border:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}th{font-family:var(--mono);font-size:11px;letter-spacing:.06em;color:var(--faint);background:var(--surface-2);white-space:nowrap}td{font-variant-numeric:tabular-nums;white-space:nowrap;max-width:36ch;overflow:hidden;text-overflow:ellipsis}
.tbl{overflow-x:auto}details{margin:10px 0}summary{cursor:pointer;font-weight:600;font-size:14px;padding:8px 0}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.up{color:var(--rise)}.down{color:var(--fall)}
footer{margin-top:60px;padding-top:16px;border-top:1px solid var(--line);color:var(--faint);font-size:12.5px;font-family:var(--mono)}
"""


def md_links(s):
    s = H.escape(str(s), quote=False)
    s = LINK.sub(lambda m: f'<a href="{H.escape(m.group(2), quote=True)}" target="_blank" rel="noopener">{m.group(1)}</a>', s)
    s = re.sub(r"(▲\d[\d,]*)", r'<span class="up">\1</span>', s)
    s = re.sub(r"(?<![\w$])(\+\d[\d,.]*%?)", r'<span class="up">\1</span>', s)
    s = re.sub(r"(?<![\w$])(−\d[\d,.]*%?)", r'<span class="down">\1</span>', s)
    return s


def badge_html(b):
    cls = "new" if b in ("신작", "출시 예정") else "excl" if b == "본문 제외" else "disc" if b.startswith("할인") or b == "세일" else ""
    return f'<span class="badge {cls}">{H.escape(b)}</span>'


def items_html(items):
    if not items:
        return '<p class="empty">해당 없음</p>'
    out = ["<ol>"]
    for it in items:
        out.append(f'<li><a class="nm" href="{H.escape(it["url"] or "#", quote=True)}" target="_blank" rel="noopener">{H.escape(it["name"])}</a> '
                   + "".join(badge_html(b) for b in it.get("badges", []))
                   + f'<span class="ln">{md_links(it["line"])}</span>' + (f'<span class="sb">{H.escape(it["sub"])}</span>' if it.get("sub") else "") + "</li>")
    out.append("</ol>")
    return "".join(out)


def table_html(t):
    head = "".join(f"<th>{H.escape(c)}</th>" for c in t["cols"])
    rows = "".join("<tr>" + "".join(f"<td>{md_links(c)}</td>" for c in r) + "</tr>" for r in t["rows"])
    return f'<div class="tbl"><table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table></div>'


def to_html(rep):
    p = rep.get("pick")
    pick = ""
    if p:
        pick = (f'<div class="card pick"><h3>오늘의 선정 게임' + (f" · {p['streak']}일 연속 ({p['since']}~)" if p["streak"] > 1 else "") + "</h3>"
                f'<p class="name"><a href="{H.escape(p["url"], quote=True)}" target="_blank" rel="noopener">{H.escape(p["name"])}</a></p>'
                f'<div class="sub">{H.escape(p.get("sub") or "")}</div>'
                f'<div class="links">' + " · ".join(f'<a href="{H.escape(u, quote=True)}" target="_blank" rel="noopener">{H.escape(t)}</a>' for t, u in p["links"]) + "</div>"
                f'<div>{md_links(p["line"])}</div><div style="margin-top:8px">' + "".join(badge_html(b) for b in p["badges"]) + "</div></div>")
    side = ('<div class="card"><h3>큰 폭 변화</h3><ul class="bul">' + "".join(f"<li>{md_links(h)}</li>" for h in rep["headline"]) + "</ul>"
            '<h3 style="margin-top:14px">특이사항</h3><ul class="bul">' + "".join(f"<li>{md_links(n)}</li>" for n in rep["notes"]) + "</ul></div>")
    status = "".join(f"<div><dt>{H.escape(k)}</dt><dd>{H.escape(v)}</dd></div>" for k, v in rep["status"])

    secs = []
    for s in rep["sections"]:
        body = []
        if s.get("text"):
            body.append(f"<p>{md_links(s['text'])}</p>")
        if s.get("blocks"):
            body.append('<div class="blocks">' + "".join(f'<div class="card block"><h4>{H.escape(b["title"])}</h4>{items_html(b["items"])}</div>' for b in s["blocks"]) + "</div>")
        if s.get("list") is not None:
            body.append('<ul class="bul">' + "".join(f"<li>{md_links(x)}</li>" for x in s["list"]) + "</ul>")
        if s.get("tables"):
            for t in s["tables"]:
                if s["no"] == "06":
                    body.append(f"<details><summary>{H.escape(t['title'])}</summary>{table_html(t)}</details>")
                else:
                    body.append((f"<h4 style='margin:14px 0 0'>{H.escape(t['title'])}</h4>" if t.get("title") else "") + table_html(t))
        secs.append(f'<section id="s{s["no"]}"><h2><span class="no">{s["no"]}</span>{H.escape(s["title"])}</h2>'
                    + (f'<p class="sbasis">{md_links(s["basis"])}</p>' if s.get("basis") else "") + "".join(body) + "</section>")

    title = f"{rep['platform_ko']} 트렌딩 · {rep['date']}"
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{H.escape(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+KR:wght@400;500;600&display=swap">
<style>{CSS}</style></head>
<body><div class="wrap">
<header><p class="eyebrow">일간 리포트 · {rep['round']}회차</p><h1>{H.escape(rep['platform_ko'])} 트렌딩 · {date_ko(rep['date'])}</h1>
<p class="basis">{H.escape(rep['basis_line'])}</p><dl class="status">{status}</dl></header>
<div class="top">{pick}{side}</div>
{''.join(secs)}
<footer>{H.escape(rep['collect_line'])} · 생성 {datetime.now().strftime('%Y-%m-%d %H:%M')} · 모든 판매·매출 숫자는 추정치이며 게임 간 비교 용도입니다.</footer>
</div></body></html>"""
