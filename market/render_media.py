"""미디어·밈 리포트 dict → markdown(dry-run 본문) · HTML(01~10) · 카드 HTML 2~3장(Threads 가 있으면 3장) · Discord 임베드.

HTML 과 카드는 design/tokens.json + market/ui.py + market/charts.py 위에 있습니다(render.daily_css("media") + 미디어 규칙 몇 줄).
KYM·Reddit 제목과 About 원문은 영어 그대로 두고, 한국어 설명(ko_what · ko_idea)과 인사이트는 Claude 가 만든 경우에만 붙습니다.
"""
import html as H
import re
from datetime import datetime, timezone, timedelta

from . import charts, headline, render, ui
from .render import date_ko, esc
from .media_analyze import KIND_KO

KST = timezone(timedelta(hours=9))
TITLE = "미디어·밈 트렌드"
TAG = "Indie Trending · Media"
SECTIONS = [("01", "틱톡·인스타 트렌드", "KYM"), ("02", "릴스·틱톡 트렌드 정리", "유튜브 '이번 주 트렌드' 정리 영상의 제목·설명에서 뽑은 항목 · 정리 영상 Top 5"),
            ("03", "새로 등록된 밈", "KYM 확정 · 제출"), ("04", "Threads 키워드 관찰", "키워드별 24시간 게시 수 · 새로 뜨는 말 · 대표 글"),
            ("05", "커뮤니티 베스트", "Reddit"), ("06", "유튜브 인기 급상승", "KR / US Top 10 · 60초 이하는 쇼츠"),
            ("07", "검색 급상승 · 세상의 관심사", "Google 트렌드 · 위키 (접힘)"), ("08", "밈 템플릿 순위 변동", "Imgflip"),
            ("09", "게임 ↔ 밈 교차", "Steam · itch"), ("10", "수집 상태", "")]
SUMMARY_LEN = 120
COLOR = 0x6B3FA0

MEDIA_CSS = """
.card{background:var(--surface);border:var(--bw) solid var(--line)}
.lbl{font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink-2);margin:0 0 var(--sp-sm)}
.pick{padding:var(--sp-lg);display:flex;flex-direction:column;gap:var(--sp-md)}
.pick .ph{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:var(--sp-lg);align-items:start}
@media(max-width:767px){.pick .ph{grid-template-columns:1fr}}
.pk-sum{margin:0;font:var(--t-body-lg-w) var(--t-body-lg) var(--font-body);color:var(--ink)}
.ko{margin:4px 0 0;font:var(--t-body-md-w) var(--t-body-md) var(--font-body);color:var(--ink)}
.ko .idea{display:block;color:var(--primary-light);font-weight:500}
.g .im{width:120px;height:120px;object-fit:cover;background:var(--surface-2);flex:none;display:block;border:var(--bw) solid var(--line)}
.g .im.sq{width:72px;height:72px}
.g .nm a{color:inherit}
.rk{font:var(--t-badge-num-w) var(--t-badge-num) var(--font-mono);color:var(--ink-3);min-width:2.2ch;text-align:right;padding-top:5px}
.g.r{grid-template-columns:auto minmax(0,1fr) auto}
.g.r .nm{font-weight:500;font-family:var(--font-body);font-size:var(--fs-body)}
.trf{font-variant-numeric:tabular-nums;white-space:nowrap}
.kpi b{font:700 var(--t-data-lg) var(--font-mono);letter-spacing:var(--t-data-lg-ls);color:var(--ink)}
.src-ok{color:var(--rise);font-weight:600}.src-fail{color:var(--fall);font-weight:600}.src-skip{color:var(--ink-2);font-weight:600}
td.wrap{white-space:normal}
details.dt .blocks{padding:var(--sp-md)}
details.ab{margin-top:4px;font:var(--t-body-sm-w) var(--t-body-sm) var(--font-body);color:var(--ink-2)}
details.ab summary{cursor:pointer;color:var(--primary-light);font-weight:500;list-style:none}
details.ab summary::-webkit-details-marker{display:none}
details.ab p{margin:4px 0 0;line-height:1.55}
.yt{width:120px;aspect-ratio:16/9;object-fit:cover;background:var(--surface-2);flex:none;display:block;border:var(--bw) solid var(--line)}
.insight{padding:var(--sp-lg);font:var(--t-body-lg-w) var(--t-body-lg) var(--font-body)}
.pc{display:flex;gap:var(--sp-md);align-items:center;flex-wrap:wrap}
ul.hl .h1{font:600 var(--t-body-md) var(--font-body)}
.th-grid{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr);gap:var(--gutter);align-items:start}
@media(max-width:767px){.th-grid{grid-template-columns:1fr}}
.th-chart{overflow-x:auto}
.th-chart svg{width:100%;height:auto;min-width:480px}
.terms{display:flex;flex-wrap:wrap;gap:6px}
.terms .lchip small{color:var(--ink-3);margin-left:4px;font-weight:500}
.post{padding:10px 0;border-top:var(--bw) solid var(--line)}
.post:first-child{border-top:0}
.post .u{font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);color:var(--ink-2)}
.post .x{margin:2px 0 0;font:var(--t-body-md-w) var(--t-body-md) var(--font-body);color:var(--ink)}
.post .x a{color:inherit}
.th-note{font:var(--t-body-sm-w) var(--t-body-sm) var(--font-body);color:var(--warn);margin:var(--sp-sm) 0 0}
.rl-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:var(--sp-md)}
@media(max-width:767px){.rl-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
.rl{background:var(--surface);border:var(--bw) solid var(--line);min-width:0;display:flex;flex-direction:column}
.rl .yt{width:100%;aspect-ratio:16/9;border:0;border-bottom:var(--bw) solid var(--line)}
.rl .t{padding:8px 10px 2px;font:600 var(--t-body-md) var(--font-body);line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;color:var(--ink)}
.rl .t a{color:inherit}
.rl .s{padding:0 10px 8px;font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.rl .s b{color:var(--ink)}
.terms .lchip.new{border-color:var(--rise);color:var(--rise)}
.terms .lchip i{font-style:normal;font-size:.8em;color:var(--ink-3);margin-left:4px}
"""

PLATFORM_CLS = {"TikTok": "acc", "Instagram": "new", "YouTube": "excl", "Twitter/X": "", "Reddit": "disc", "Twitch": "acc"}
STATUS_KO = {"confirmed": "확정", "submission": "제출", "deadpool": "데드풀", "researching": "조사 중"}


def _sum(s, n=SUMMARY_LEN):
    """n 글자로 자른 뒤 마지막 문장 경계(. ! ?)에서 끊습니다. 경계가 너무 앞이면(절반 미만) 글자 수에서 끊고 '…'."""
    s = (s or "").strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    best = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind(".\n"))
    if best >= n * 0.5:
        return cut[: best + 1]
    return cut.rstrip(" ,;:") + "…"


def _fmt_traffic(x):
    return x.get("traffic_raw") or (f"{x.get('traffic', 0):,}+" if x.get("traffic") else "—")


def _arrow(d):
    if d is None:
        return ""
    return f"▲{d}" if d > 0 else (f"▼{-d}" if d < 0 else "—")


def _kst(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone(KST).strftime("%m-%d %H:%M")
    except (TypeError, ValueError):
        return iso or ""


def _when(x):
    return x.get("published") or x.get("modified") or ""


def _mdsafe(s):
    return (s or "").replace("[", "［").replace("]", "］").replace("*", "＊").replace("_", "＿").replace("`", "'")


def _views(n):
    if n is None:
        return "—"
    return f"{n / 1_000_000:.1f}M" if n >= 1_000_000 else (f"{n / 1_000:.0f}K" if n >= 1_000 else str(n))


def _kinds_ko(x):
    """출처 표시. 확정·제출 엔트리는 상태 배지가 따로 있으므로 뉴스피드·검색만 적고, 그것뿐이면 '엔트리'."""
    kinds = [k for k in x.get("kinds") or [] if k not in ("confirmed", "submissions")]
    return " · ".join(dict.fromkeys(KIND_KO.get(k, k) for k in kinds)) or "엔트리"


def _flags(x):
    out = []
    if x.get("status"):
        out.append(STATUS_KO.get(x["status"], x["status"]))
    if x.get("new"):
        out.append("신규")
    elif x.get("updated_only"):
        out.append("갱신")
    return out


def _cross_line(c):
    return f"{c['term']} → {c['game']} ({'Steam' if c['platform'] == 'steam' else 'itch'}) · {c['source']}"


def has_llm(rep):
    return bool(rep.get("insight")) or any(x.get("ko_what") for x in rep.get("kym_all") or [])


# ---------- Threads 키워드 관찰 ----------

ENV_RX = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b")


def _note_md(note):
    """메모의 환경 변수 이름(REPO_SECRETS_PAT 등)은 밑줄이 기울임으로 바뀌지 않게 코드 글꼴로."""
    return ENV_RX.sub(r"`\1`", note or "")


def _th_delta(x):
    """전날 대비 표시: ▲3 · ▼2 · — · (비교 없음이면 빈 문자열)."""
    if x.get("delta") is None:
        return ""
    return _arrow(x["delta"])


def _th_count(x):
    return f"{x['recent']}+" if x.get("saturated") else str(x["recent"])


def _th_rows(th, n=10):
    """charts.bar_lift 용 [(키워드, 24시간 게시 수, 배율|None)]."""
    return [(x["keyword"], x["recent"], x.get("lift")) for x in th["keywords"][:n]]


def _th_term_line(th, n=8, md=False):
    out = []
    for t in th.get("rising") or []:
        label = _mdsafe(t["term"]) if md else t["term"]
        out.append(f"{label}({t['prev']}→{t['n']})" if t.get("prev") is not None else f"{label}({t['n']})")
        if len(out) >= n:
            break
    return " · ".join(out)


def _th_samples(th, n=3):
    """키워드 순서대로 대표 글을 하나씩 돌아가며 n 개 (TOP 우선은 분석 단계에서 정렬됨)."""
    out, seen = [], set()
    for depth in range(3):
        for row in th["keywords"]:
            if len(out) >= n:
                return out
            sp = row["sample"][depth] if len(row["sample"]) > depth else None
            if sp and sp["id"] not in seen:
                seen.add(sp["id"])
                out.append({**sp, "keyword": row["keyword"]})
    return out


def _md_threads(rep):
    th = rep.get("threads") or {}
    L = ["## 04 Threads 키워드 관찰"]
    if th.get("status") != "ok":
        L.append(f"- {th.get('note') or ('실패 · ' + th.get('error', '') if th.get('status') == 'fail' else '건너뜀')}")
        return L + [""]
    L.append(f"24시간 게시 수 (키워드 {th['n_ok']}개 · 글 {th['total_posts']}건 · 호출 {th.get('calls', 0)}회" + (" · 전날 대비" if th.get("compared") else " · 비교 대상 없음") + ")")
    L += [f"- {x['keyword']}: {_th_count(x)}" + (f" {_th_delta(x)}" if _th_delta(x) else "") for x in th["keywords"][:15]]
    if th.get("rising"):
        L.append("새로 뜨는 말: " + _th_term_line(th, 10))
    for sp in _th_samples(th, 3):
        L.append(f"- [{sp['keyword']}] @{sp['username']}: {sp['text']} {sp['url']}")
    if th.get("failed"):
        L.append("실패 키워드: " + ", ".join(f"{f['keyword']}({f['error'][:40]})" for f in th["failed"][:5]))
    if th.get("note"):
        L.append(f"메모: {th['note']}")
    return L + [""]


# ---------- 릴스·틱톡 트렌드 정리 ----------

RL_KIND_KO = {"list": "목록", "phrase": "구절", "hashtag": "태그"}


def _rl_rows(rl, n=8):
    """charts.bar_lift 용 [(항목, 등장 영상 수, 전날 대비 배율|None)]."""
    return [(x["term"], x["n"], x.get("lift")) for x in rl["items"][:n]]


def _rl_term_line(rl, n=8, md=False):
    out = []
    for x in rl.get("items") or []:
        label = _mdsafe(x["term"]) if md else x["term"]
        out.append(f"{label}({x['n']}채널)" + (" NEW" if x.get("new") else ""))
        if len(out) >= n:
            break
    return " · ".join(out)


def _rl_dur(v):
    d = v.get("duration")
    return f"{d // 60}:{d % 60:02d}" if isinstance(d, int) else "—"


def _md_reels(rep):
    rl = rep.get("reels") or {}
    L = ["## 02 릴스·틱톡 트렌드 정리 (유튜브 정리 영상)"]
    if rl.get("status") != "ok":
        L.append(f"- {rl.get('note') or ('실패 · ' + rl.get('error', '') if rl.get('status') == 'fail' else '건너뜀')}")
        return L + [""]
    L.append(f"검색어 {rl['n_queries_ok']}/{len(rl['queries'])}개 · 최근 {rl['days']}일 · 검색 결과 {rl.get('n_found', 0)}편 중 정리 영상 {rl['n_videos']}개 · 항목 {rl['n_items']} · 호출 search {rl['calls']['search']}·videos {rl['calls']['videos']} ({rl['calls']['units']}유닛)"
             + (" · 전날 대비" if rl.get("compared") else " · 비교 대상 없음"))
    L.append("트렌드 항목 Top 8: " + (_rl_term_line(rl, 8) or "없음"))
    L += [f"{v['rank']}. {v['title']} · {v['channel']} · {_views(v['views'])} · {_rl_dur(v)}" + (" · NEW" if v.get("new") else "") + f" {v['url']}" for v in rl["videos"][:5]]
    fails = [q for q in rl["queries"] if q.get("error")]
    if fails:
        L.append("실패 검색어: " + ", ".join(f"{q['q']}({q['error'][:40]})" for q in fails))
    return L + [""]


# ====================================================================
# markdown (dry-run 본문)
# ====================================================================

def _md_item(x):
    L = [f"- [{x['title']}]({x['url']}) · {' · '.join(x.get('platforms') or []) or '플랫폼 미상'} · {_kinds_ko(x)}" + "".join(f" · {f}" for f in _flags(x)) + f" · {_kst(_when(x))}"]
    if x.get("ko_what"):
        L.append(f"  {x['ko_what']}")
    if x.get("ko_idea"):
        L.append(f"  → 활용: {x['ko_idea']}")
    return L


def to_md(rep):
    L = [f"# {TITLE} · {date_ko(rep['date'])} · {rep['round']}회차", ""]
    p = rep.get("pick")
    if p:
        streak = f" · {p['streak']}일 연속" if p.get("streak", 1) > 1 else ""
        L.append(f"**오늘의 트렌드 → [{p['title']}]({p['url']})**{streak} · {' · '.join(p.get('platforms') or []) or '플랫폼 미상'} · {p['reason']}")
        if p.get("ko_what"):
            L.append(f"> {p['ko_what']}")
        elif p.get("summary"):
            L.append(f"> {_sum(p['summary'])}")
    else:
        L.append("오늘의 트렌드: KYM 항목 없음")
    L.append("플랫폼 집계: " + (" · ".join(f"{a} {n}건" for a, n in rep["platform_counts"]) or "없음") + f" · KYM {len(rep['kym_all'])}건 (신규 {rep['kym_new']})")
    if rep.get("insight"):
        L += ["", f"**오늘의 인사이트** {rep['insight']}"]
    L += ["", "## 01 틱톡·인스타 트렌드 (KYM)"]
    for x in rep["shortform"][:12]:
        L += _md_item(x)
    L += [""] if rep["shortform"] else ["- 없음", ""]
    L += _md_reels(rep)
    L.append("## 03 새로 등록된 밈 (KYM 확정 · 제출)")
    for x in rep["new_memes"][:12]:
        L += _md_item(x)
    L += [""] if rep["new_memes"] else ["- 없음", ""]
    L += _md_threads(rep)
    L.append("## 05 커뮤니티 베스트 (Reddit)")
    for r in rep["reddit"]:
        if r["status"] != "ok":
            L.append(f"- r/{r['sub']}: 실패 ({r.get('error', '')})")
            continue
        L.append(f"**r/{r['sub']}**")
        L += [f"- [{x['title']}]({x['url']})" for x in r["items"][:5]]
    L += ["", "## 06 유튜브 인기 급상승 Top 10"]
    for region in ("KR", "US"):
        y = rep["youtube"][region]
        if y["status"] != "ok":
            L.append(f"- {region}: {'건너뜀' if y['status'] == 'skip' else '실패'} ({y.get('error', '')})")
            continue
        L.append(f"**{region}** (인기 {y['total']}개 중 쇼츠 {y['shorts']})")
        L += [f"{v['rank']}. {v['title']} · {v['channel']} · {_views(v['views'])}" + (" · 쇼츠" if v.get("shorts") else "") for v in y["items"][:10]]
    L += ["", "## 07 검색 급상승 · 세상의 관심사 (제외 필터 적용)"]
    for geo in ("KR", "US"):
        L.append(f"**검색 {geo}** (제외 {rep['filtered'].get('trends_' + geo.lower(), 0)}건)")
        L += [f"{x['rank']}. {x['title']} · {_fmt_traffic(x)}" + (f" · {x['days']}일 연속" if x.get("days", 1) > 1 else "") + (f" · {x['news_title']}" if x.get("news_title") else "") for x in rep["trends"][geo]] or ["- 없음"]
    for proj in ("en", "ko"):
        L.append(f"**위키 {proj}** ({rep['wiki'].get(proj + '_day', '')} 집계, 제외 {rep['filtered'].get('wiki_' + proj, 0)}건)")
        L += [f"{x['rank']}. {x['title']} · {x['views']:,}" + (f" · {x['days']}일 연속" if x.get("days", 1) > 1 else "") for x in rep["wiki"][proj][:10]]
    L += ["", "## 08 밈 템플릿 순위 변동 (Imgflip)"]
    im = rep["imgflip"]
    if im["compared"]:
        L += [f"- {x['name']} {x['prev_rank']}→{x['rank']}위 {_arrow(x['delta'])}" for x in im["movers"][:10]] or ["- 상위 30 변동 없음"]
        L.append("신규 진입: " + (", ".join(f"{x['name']}({x['rank']}위)" for x in im["entered"]) or "없음"))
        L.append("이탈: " + (", ".join(f"{x['name']}(어제 {x['prev_rank']}위)" for x in im["exited"]) or "없음"))
    else:
        L.append("비교 대상 없음 (회차 1). 오늘 상위: " + ", ".join(x["name"] for x in im["items"][:10]))
    L += ["", "## 09 게임 ↔ 밈 교차"]
    L += [f"- {_cross_line(c)}" for c in rep["cross"]] or ["- 없음"]
    L += ["", "## 10 수집 상태"]
    L += [f"- {s['label']}: {dict(ok='정상', fail='실패', skip='건너뜀').get(s['status'], s['status'])} · {s['count']}개" + (f" · 제외 {s['filtered']}" if s.get("filtered") else "") + (f" · {s['error']}" if s.get("error") else "") for s in rep["sources"]]
    u = rep.get("llm_usage")
    if u:
        L.append(f"- Claude 설명·인사이트: {'정상' if u.get('ok') else '없음 (' + (u.get('error') or '') + ')'} · input {u.get('input_tokens', 0)} · output {u.get('output_tokens', 0)} 토큰")
    L += ["", rep["collect_line"]]
    return "\n".join(L) + "\n"


# ====================================================================
# HTML
# ====================================================================

def _a(text, url):
    return f'<a href="{H.escape(url or "", quote=True)}" target="_blank" rel="noopener">{esc(text)}</a>' if url else esc(text)


def _pills(platforms, extra=()):
    out = [f'<span class="badge {PLATFORM_CLS.get(p, "")}">{esc(p)}</span>' for p in platforms or []]
    out += [f'<span class="badge">{esc(e)}</span>' for e in extra if e]
    return f'<div class="pills">{"".join(out)}</div>' if out else ""


def _ko_html(x):
    if not (x.get("ko_what") or x.get("ko_idea")):
        return ""
    return f'<p class="ko">{esc(x.get("ko_what", ""))}' + (f'<span class="idea">→ 활용: {esc(x["ko_idea"])}</span>' if x.get("ko_idea") else "") + "</p>"


def _about_html(x):
    return f'<details class="ab"><summary>About (영어 원문)</summary><p>{esc(x["about"])}</p></details>' if x.get("about") else ""


def _pick_html(p, rep):
    if not p:
        return '<div class="card side"><p class="seclabel">오늘의 트렌드</p><p class="empty">최근 48시간 KYM 항목이 없습니다.</p></div>'
    streak = f"{p['streak']}일 연속" if p.get("streak", 1) > 1 else "오늘"
    body = _ko_html(p) or f'<p class="pk-sum">{esc(_sum(p.get("about") or p.get("summary"), 260))}</p>'
    chips = [f'<span class="lchip">{esc(a)}</span>' for a in (p.get("platforms") or [])[:3]] + [f'<span class="lchip ghost">{esc(f)}</span>' for f in _flags(p)[:2]]
    hero = render.image_hero_html(p.get("image"), f'<span class="ov tl">{"".join(chips)}</span>' if chips else "", name=p["title"], url=p["url"])
    donut = charts.donut([(a, n) for a, n in rep["platform_counts"][:3]] + ([("기타", sum(n for _, n in rep["platform_counts"][3:]))] if len(rep["platform_counts"]) > 3 else []),
                         width=360, height=170, scale="web", center_label="KYM 건", title="플랫폼 집계")
    return (f'<article class="panel pick"><div class="kick"><span class="lchip pos">TODAY\'S TREND</span><span class="seclabel">KYM · {esc(streak)} · {esc(p.get("reason", ""))}</span></div>'
            f'<h2 class="hl">{headline.to_html(headline.media_pick(p), link=p["url"])}</h2>{hero}'
            f'<div class="ph"><div>{body}{_about_html(p)}<p class="pk-sub" style="margin-top:var(--sp-sm);font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);color:var(--ink-2)">KYM {esc(_kinds_ko(p))} · {esc(_kst(_when(p)))} KST</p></div>'
            f'<div class="panel" style="padding:var(--sp-md)"><p class="seclabel">플랫폼 집계 · KYM {len(rep["kym_all"])}건 · 신규 {rep["kym_new"]}</p>{donut}</div></div></article>')


def _side_html(rep):
    quick = []
    memes = rep["new_memes"][:3]
    quick.append('<li class="nothumb"><div><div class="h1">새로 등록된 밈 ' + f'{len(rep["new_memes"])}건</div><div class="h2">' + ("".join(f"<span>{esc(x['title'])}</span>" for x in memes) or "<span>최근 48시간 없음</span>") + "</div></div></li>")
    rd = [r for r in rep["reddit"] if r["status"] == "ok" and r["items"]][:3]
    quick.append('<li class="nothumb"><div><div class="h1">커뮤니티 베스트</div><div class="h2">' + ("".join(f"<span>r/{esc(r['sub'])} · {esc(r['items'][0]['title'][:50])}</span>" for r in rd) or "<span>수집 실패</span>") + "</div></div></li>")
    y = (rep.get("youtube") or {}).get("KR") or {}
    if y.get("status") == "ok":
        quick.append('<li class="nothumb"><div><div class="h1">유튜브 KR 인기 Top 3</div><div class="h2">' + "".join(f"<span>{v['rank']}. {esc(v['title'][:40])}</span>" for v in y["items"][:3]) + "</div></div></li>")
    rl = rep.get("reels") or {}
    if rl.get("status") == "ok" and rl.get("items"):
        quick.append('<li class="nothumb"><div><div class="h1">릴스·틱톡 트렌드 Top 3</div><div class="h2">' + "".join(f"<span>{esc(x['term'][:40])} · {x['n']}채널</span>" for x in rl["items"][:3]) + "</div></div></li>")
    others = [x for x in rep["shortform"] if not rep.get("pick") or x["url"] != rep["pick"]["url"]][:3]
    quick.append('<li class="nothumb"><div><div class="h1">다른 틱톡·인스타 트렌드</div><div class="h2">' + ("".join(f"<span>{esc(x['title'][:50])}</span>" for x in others) or "<span>없음</span>") + "</div></div></li>")
    return f'<aside class="panel side"><p class="seclabel">AT A GLANCE</p><ul class="hl">{"".join(quick)}</ul></aside>'


def _insight_html(rep):
    if not rep.get("insight"):
        return ""
    return f'<div class="panel insight" style="margin-top:var(--gutter)"><p class="seclabel" style="margin-bottom:var(--sp-sm)">오늘의 인사이트 · Claude</p>{esc(rep["insight"])}</div>'


def _kym_rows(items, empty):
    rows = []
    for x in items:
        im = f'<img class="im" src="{H.escape(x["image"], quote=True)}" alt="" loading="lazy">' if x.get("image") else '<span class="im"></span>'
        rows.append(f'<div class="g">{im}<div class="gb"><div class="gh"><div class="nm">{_a(x["title"], x["url"])}</div></div>'
                    f'<div class="sub">{esc(_sum(x.get("summary"), 200))}</div>{_ko_html(x)}{_pills(x.get("platforms"), _flags(x))}{_about_html(x)}'
                    f'<div class="meta"><span>KYM {esc(_kinds_ko(x))}</span><span>{esc(_kst(_when(x)))} KST</span></div></div></div>')
    return f'<div class="card block">{"".join(rows)}</div>' if rows else f'<p class="empty">{esc(empty)}</p>'


def _rank_rows(items, line):
    return "".join(f'<div class="g r"><div class="rk">{x["rank"]}</div>{line(x)}</div>' for x in items) or '<p class="empty">없음</p>'


def _trend_row(x):
    days = f'<span class="badge acc">{x["days"]}일 연속</span>' if x.get("days", 1) > 1 else ""
    return (f'<div class="gb"><div class="nm">{_a(x["title"], x["url"])} {days}</div>'
            + (f'<div class="sub">{_a(x["news_title"], x["news_url"])}</div>' if x.get("news_title") else "") + f'</div><div class="kpi"><b class="trf">{esc(_fmt_traffic(x))}</b></div>')


def _wiki_row(x):
    delta = x["prev_rank"] - x["rank"] if x.get("prev_rank") else None
    bits = [f'<span class="badge acc">{x["days"]}일 연속</span>' if x.get("days", 1) > 1 else "",
            f'<span class="{"up" if (delta or 0) > 0 else "down" if (delta or 0) < 0 else ""}">{_arrow(delta)}</span>' if delta is not None else ""]
    return f'<div class="gb"><div class="nm">{_a(x["title"], x["url"])} {" ".join(b for b in bits if b)}</div></div><div class="kpi"><b>{x["views"]:,}</b><small>조회</small></div>'


def _blocks(parts):
    return f'<div class="blocks">{"".join(f"<div class=\"card block\"><h4>{esc(lbl)}</h4>{body}</div>" for lbl, body in parts)}</div>'


def _threads_html(rep):
    th = rep.get("threads") or {}
    if th.get("status") == "skip":
        return ('<p class="empty">THREADS_ACCESS_TOKEN 이 없어 건너뜀. README 의 "Threads 토큰 만드는 법" 절을 따라 장기 토큰을 Secrets 에 넣으면 이 자리에 키워드별 게시량이 나옵니다.</p>'
                + (f'<p class="th-note">{esc(th["note"])}</p>' if th.get("note") and th["note"] != "Threads: 토큰 없음" else ""))
    if th.get("status") != "ok":
        return f'<p class="empty">수집 실패 · {esc(th.get("error", ""))}</p>' + (f'<p class="th-note">{esc(th["note"])}</p>' if th.get("note") else "")
    cmp_txt = "전날 대비 배율" if th.get("compared") else "비교 대상 없음(첫 회차)"
    chart = charts.bar_lift(_th_rows(th, 10), width=936, height=max(260, 46 * min(10, len(th["keywords"]))), scale="web", max_rows=10, label_chars=14,
                            title="Threads 키워드별 24시간 게시 수")
    terms = "".join(f'<span class="lchip{" pos" if (t.get("delta") or 0) >= 3 else ""}">{esc(t["term"])}<small>{(str(t["prev"]) + "→") if t.get("prev") is not None else ""}{t["n"]}</small></span>' for t in th.get("rising") or [])
    samples = "".join(f'<div class="post"><div class="u">{esc(sp["keyword"])} · @{esc(sp["username"])} · {esc(_kst(sp["timestamp"]))} KST' + (" · TOP" if sp.get("from") == "top" else "") + f'</div><p class="x">{_a(sp["text"], sp["url"])}</p></div>'
                      for sp in _th_samples(th, 6)) or '<p class="empty">본문이 있는 글이 없습니다.</p>'
    table = "".join(f'<tr><td class="wrap">{esc(x["keyword"])}</td><td class="num">{esc(_th_count(x))}</td><td class="num">{x["prev"] if x.get("prev") is not None else "—"}</td>'
                    f'<td class="num {"up" if (x.get("delta") or 0) > 0 else "down" if (x.get("delta") or 0) < 0 else ""}">{esc(_th_delta(x) or "—")}</td><td class="num">{x["top_n"]}/{x["recent_n"]}</td>'
                    f'<td class="wrap">{_a(x["sample"][0]["text"], x["sample"][0]["url"]) if x["sample"] else "—"}</td></tr>' for x in th["keywords"])
    failed = (f'<p class="stext">실패 키워드 {len(th["failed"])}개: ' + ", ".join(f"{esc(f['keyword'])}({esc(f['error'][:50])})" for f in th["failed"][:8]) + "</p>") if th.get("failed") else ""
    note = f'<p class="th-note">{esc(th["note"])}</p>' if th.get("note") else ""
    head = (f'<p class="stext">키워드 {th["n_ok"]}개 · 글 {th["total_posts"]}건 · 호출 {th.get("calls", 0)}회(하루 한도 2,200) · {cmp_txt}. '
            f'24시간 게시 수는 RECENT 검색 {th["limit"]}건 기준이라 {th["limit"]}+ 는 포화입니다. 남의 글에는 좋아요 수가 없어 게시량과 말의 변화만 봅니다.</p>')
    return (head + note + f'<div class="th-grid"><div class="card block"><h4>24시간 게시 수 Top 10 · 초록 = 전날의 1.5배 이상</h4><div class="th-chart">{chart}</div></div>'
            f'<div class="card block"><h4>새로 뜨는 말 · 글 3건 이상, 전날 대비 증가순</h4>' + (f'<div class="terms">{terms}</div>' if terms else '<p class="empty">아직 없음</p>') + "</div></div>"
            f'<div class="card block" style="margin-top:var(--gutter)"><h4>대표 글 (TOP 우선 · 답글 제외 · 120자)</h4>{samples}</div>{failed}'
            f'<details class="dt"><summary>키워드 {len(th["keywords"])}개 전체</summary><div class="tbl"><table><thead><tr><th>키워드</th><th class="num">24h</th><th class="num">어제</th><th class="num">변동</th><th class="num">TOP/RECENT</th><th>대표 글</th></tr></thead><tbody>{table}</tbody></table></div></details>')


def _reels_html(rep):
    rl = rep.get("reels") or {}
    if rl.get("status") == "skip":
        return ('<p class="empty">YOUTUBE_API_KEY 가 없어 건너뜀. README 의 "유튜브" 절을 따라 키를 Secrets 에 넣으면 이 자리에 "이번 주 릴스·틱톡 트렌드" 정리 영상에서 뽑은 항목이 나옵니다.</p>'
                + (f'<p class="th-note">{esc(rl["note"])}</p>' if rl.get("note") else ""))
    if rl.get("status") != "ok":
        return f'<p class="empty">수집 실패 · {esc(rl.get("error", ""))}</p>'
    cmp_txt = "배율 = 전날 대비 등장 채널 수" if rl.get("compared") else "비교 대상 없음(첫 회차)"
    chart = charts.bar_lift(_rl_rows(rl, 8), width=936, height=max(240, 46 * min(8, len(rl["items"]))), scale="web", max_rows=8, label_chars=16,
                            title="트렌드 항목별 등장 채널 수")
    chips = "".join(f'<span class="lchip{" new" if x.get("new") else ""}">{esc(x["term"])}<small>{x["n"]}채널</small>' + (" <i>NEW</i>" if x.get("new") else f' <i>{RL_KIND_KO.get(x["kind"], "")}</i>') + "</span>"
                    for x in rl["items"][:8])
    tiles = "".join(f'<div class="rl"><img class="yt" src="{H.escape(v.get("thumb", ""), quote=True)}" alt="" loading="lazy"><div class="t">{_a(v["title"], v["url"])}</div>'
                    f'<div class="s"><b>{esc(_views(v["views"]))}</b> · {esc(v["channel"])} · {esc(_rl_dur(v))}' + (' · <span class="up">NEW</span>' if v.get("new") else "") + "</div></div>"
                    for v in rl["videos"][:5]) or '<p class="empty">영상 없음</p>'
    vt = "".join(f'<tr><td class="num">{v["rank"]}</td><td class="wrap">{_a(v["title"], v["url"])}' + (' <span class="badge acc">NEW</span>' if v.get("new") else "") + (' <span class="badge">쇼츠</span>' if v.get("shorts") else "")
                 + f'</td><td class="wrap">{esc(v["channel"])}</td><td class="num">{v["views"]:,}</td><td class="num">{esc(_rl_dur(v))}</td><td class="num">{esc(_kst(v["published"]))}</td><td class="wrap">{esc(" / ".join(v.get("queries") or []))}</td></tr>'
                 for v in rl["videos"])
    it = "".join(f'<tr><td class="wrap">{esc(x["term"])}' + (' <span class="badge acc">NEW</span>' if x.get("new") else "") + f'</td><td>{esc(RL_KIND_KO.get(x["kind"], x["kind"]))}</td><td class="num">{x["n"]} / {x.get("n_videos", x["n"])}</td>'
                 f'<td class="num">{x["prev"] if x.get("prev") is not None else "—"}</td><td class="num">{esc(_views(x["views"]))}</td></tr>' for x in rl["items"])
    fails = [q for q in rl["queries"] if q.get("error")]
    failed = (f'<p class="stext" style="margin-top:var(--sp-md)">실패 검색어 {len(fails)}개: ' + ", ".join(f"{esc(q['q'])}({esc(q['error'][:50])})" for q in fails[:8]) + "</p>") if fails else ""
    drop = ", ".join(f"{esc(k)} {n}" for k, n in sorted((rl.get("dropped") or {}).items(), key=lambda kv: -kv[1]))
    head = (f'<p class="stext">검색어 {rl["n_queries_ok"]}/{len(rl["queries"])}개 × 최근 {rl["days"]}일 {"관련도순" if rl.get("order", "relevance") == "relevance" else "조회수순"} · 검색 결과 {rl.get("n_found", 0)}편 중 정리 영상 {rl.get("n_roundup", 0)}편'
            + (f'(채널당 상한 적용 → {rl["n_videos"]}편)' if rl.get("n_roundup", 0) != rl["n_videos"] else "") + f' · 항목 {rl["n_items"]}개 · '
            f'YouTube API search {rl["calls"]["search"]}회 + videos {rl["calls"]["videos"]}회 = {rl["calls"]["units"]}유닛(하루 10,000) · {cmp_txt}. '
            f'정리 영상 = 제목에 trend·sound·challenge·챌린지·음원·모음 같은 말이 있고 해시태그 도배·리믹스가 아닌 것' + (f'(제외: {drop})' if drop else "") + '. '
            f'항목은 영상 설명의 번호·글머리·타임스탬프 줄, 해시태그, challenge/sound/챌린지/필터 같은 말이 붙은 구절이고, 등장 채널 수는 그 항목이 나온 서로 다른 채널의 수입니다(홍보 문구·일반어만 있는 줄은 뺌).</p>')
    return (head + f'<div class="th-grid"><div class="card block"><h4>트렌드 항목 Top 8 · 등장 채널 수 · 초록 = 전날의 1.5배 이상</h4><div class="th-chart">{chart}</div></div>'
            f'<div class="card block"><h4>항목 · NEW = 어제 정리 영상에 없던 것</h4>' + (f'<div class="terms">{chips}</div>' if chips else '<p class="empty">아직 없음</p>') + "</div></div>"
            f'<div class="card block" style="margin-top:var(--gutter)"><h4>정리 영상 Top 5 · 조회수순</h4><div class="rl-grid">{tiles}</div></div>{failed}'
            f'<details class="dt"><summary>정리 영상 {len(rl["videos"])}개 · 항목 {len(rl["items"])}개 전체</summary><div class="tbl">'
            f'<table><thead><tr><th class="num">#</th><th>영상</th><th>채널</th><th class="num">조회</th><th class="num">길이</th><th class="num">공개 (KST)</th><th>검색어</th></tr></thead><tbody>{vt}</tbody></table>'
            f'<table style="margin-top:var(--sp-md)"><thead><tr><th>항목</th><th>종류</th><th class="num">채널 / 영상</th><th class="num">어제</th><th class="num">조회 합</th></tr></thead><tbody>{it}</tbody></table></div></details>')


def _reddit_html(rep):
    parts = []
    for r in rep["reddit"]:
        body = (f'<p class="empty">수집 실패 · {esc(r.get("error", ""))}</p>' if r["status"] != "ok"
                else "".join(f'<div class="g r"><div class="rk">{x["rank"]}</div><div class="gb"><div class="nm">{_a(x["title"], x["url"])}</div></div></div>' for x in r["items"]))
        parts.append((f"r/{r['sub']}", body))
    return _blocks(parts)


def _youtube_html(rep):
    parts = []
    for region in ("KR", "US"):
        y = rep["youtube"][region]
        if y["status"] == "skip":
            body = '<p class="empty">YOUTUBE_API_KEY 가 없어 건너뜀. README 의 "유튜브" 절 참고.</p>'
        elif y["status"] != "ok":
            body = f'<p class="empty">수집 실패 · {esc(y.get("error", ""))}</p>'
        else:
            body = "".join(f'<div class="g"><img class="yt" src="{H.escape(v.get("thumb", ""), quote=True)}" alt="" loading="lazy"><div class="gb"><div class="gh"><div class="nm">{v["rank"]}. {_a(v["title"], v["url"])}' + (' <span class="badge acc">쇼츠</span>' if v.get("shorts") else "") + f'</div><div class="kpi"><b>{esc(_views(v["views"]))}</b><small>조회</small></div></div><div class="meta"><span>{esc(v["channel"])}</span><span>{v["duration"] if v.get("duration") is not None else "—"}초</span></div></div></div>' for v in y["items"]) or '<p class="empty">항목 없음</p>'
            body += f'<p class="sbasis" style="margin:10px 0 6px">인기 {y["total"]}개 중 60초 이하 {y["shorts"]}개</p>'
        parts.append((f"{region}", body))
    return _blocks(parts)


def _search_wiki_html(rep):
    inner = _blocks([("검색 급상승 KR", _rank_rows(rep["trends"]["KR"], _trend_row)), ("검색 급상승 US", _rank_rows(rep["trends"]["US"], _trend_row))])
    inner += _blocks([(f"영어 위키백과 · {rep['wiki'].get('en_day', '')} 집계" + (" (전날과 같은 집계)" if rep["wiki"].get("en_same") else ""), _rank_rows(rep["wiki"]["en"], _wiki_row)),
                      (f"한국어 위키백과 · {rep['wiki'].get('ko_day', '')} 집계" + (" (전날과 같은 집계)" if rep["wiki"].get("ko_same") else ""), _rank_rows(rep["wiki"]["ko"], _wiki_row))])
    f = rep["filtered"]
    n = f.get("trends_kr", 0) + f.get("trends_us", 0) + f.get("wiki_en", 0) + f.get("wiki_ko", 0)
    return (f'<p class="stext">정치·경제·스포츠·사건사고 키워드로 {n}건을 걸렀습니다(사람 이름은 못 거르므로 남는 것이 있습니다). 키워드는 config.json 의 media.exclude_keywords 에서 추가할 수 있습니다.</p>'
            f'<details class="dt"><summary>검색 급상승 KR {len(rep["trends"]["KR"])} · US {len(rep["trends"]["US"])} · 위키 en {len(rep["wiki"]["en"])} · ko {len(rep["wiki"]["ko"])}</summary><div class="tbl">{inner}</div></details>')


def _imgflip_html(rep):
    im = rep["imgflip"]

    def row(x, cap):
        d = x.get("delta")
        kpi = f'<div class="kpi {"up" if (d or 0) > 0 else "down" if (d or 0) < 0 else ""}"><b>{esc(_arrow(d)) if d is not None else ("신규" if x.get("new") else "—")}</b><small>{esc(cap)}</small></div>'
        return f'<div class="g"><img class="im sq" src="{H.escape(x["url"], quote=True)}" alt="" loading="lazy"><div class="gb"><div class="gh"><div class="nm">{x["rank"]}. {_a(x["name"], x["url"])}</div>{kpi}</div></div></div>'

    if not im["compared"]:
        return f'<p class="stext">비교 대상이 없습니다(회차 1). 오늘 순위만 보여 줍니다.</p><div class="card block">{"".join(row(x, "") for x in im["items"][:10])}</div>'
    movers = "".join(row(x, f"{x['prev_rank']}→{x['rank']}위") for x in im["movers"][:10]) or '<p class="empty">상위 30 안에서 순위 변동이 없습니다.</p>'
    entered = ", ".join(f"{esc(x['name'])} ({x['rank']}위)" for x in im["entered"]) or "없음"
    exited = ", ".join(f"{esc(x['name'])} (어제 {x['prev_rank']}위)" for x in im["exited"]) or "없음"
    table = "".join(f'<tr><td class="num">{x["rank"]}</td><td class="wrap">{_a(x["name"], x["url"])}</td><td class="num">{x["prev_rank"] or "—"}</td><td class="num {"up" if (x["delta"] or 0) > 0 else "down" if (x["delta"] or 0) < 0 else ""}">{esc(_arrow(x["delta"]) if x["delta"] is not None else "신규")}</td><td class="num">{(x.get("captions") or 0):,}</td></tr>' for x in im["items"])
    return (_blocks([(f"순위 변동 Top 10 (상위 {len(im['items'])} 안)", movers), ("신규 진입 · 이탈 (100개 기준)", f'<p class="stext"><b>신규 진입</b> {entered}</p><p class="stext"><b>이탈</b> {exited}</p>')])
            + f'<details class="dt"><summary>상위 {len(im["items"])} 전체</summary><div class="tbl"><table><thead><tr><th class="num">#</th><th>템플릿</th><th class="num">어제</th><th class="num">변동</th><th class="num">캡션 수</th></tr></thead><tbody>{table}</tbody></table></div></details>')


def _cross_html(rep):
    if not rep["cross"]:
        return '<p class="empty">오늘은 검색·위키·Reddit·유튜브·KYM 제목과 겹치는 Steam·itch 게임이 없습니다.</p>'
    rows = "".join(f'<div class="g r"><div class="rk">{i}</div><div class="gb"><div class="nm">{_a(c["term"], c["url"])} → {_a(c["game"], c["game_url"])} <span class="badge {"acc" if c["platform"] == "steam" else "disc"}">{"Steam" if c["platform"] == "steam" else "itch"}</span></div><div class="sub">{esc(c["source"])}</div></div></div>' for i, c in enumerate(rep["cross"], 1))
    return f'<div class="card block">{rows}</div>'


def _status_html(rep):
    ko = {"ok": "정상", "fail": "실패", "skip": "건너뜀"}
    rows = "".join(f'<tr><td>{esc(s["label"])}</td><td class="src-{s["status"]}">{ko.get(s["status"], s["status"])}</td><td class="num">{s["count"]}</td><td class="num">{s.get("filtered") or ""}</td><td class="wrap">{esc(s.get("error", ""))}</td></tr>' for s in rep["sources"])
    u = rep.get("llm_usage")
    if u:
        rows += f'<tr><td>Claude 설명·인사이트 ({esc(u.get("model") or "")})</td><td class="{"src-ok" if u.get("ok") else "src-skip"}">{"정상" if u.get("ok") else "없음"}</td><td class="num">{u.get("input_tokens", 0):,} / {u.get("output_tokens", 0):,} 토큰</td><td></td><td class="wrap">{esc(u.get("error") or "")}</td></tr>'
    return f'<div class="tbl solo"><table><thead><tr><th>소스</th><th>상태</th><th class="num">개수</th><th class="num">제외</th><th>비고</th></tr></thead><tbody>{rows}</tbody></table></div>'


def to_html(rep):
    bodies = {"01": _kym_rows(rep["shortform"], "최근 48시간에 TikTok·Instagram 태그가 붙은 KYM 항목이 없습니다."),
              "02": _reels_html(rep), "03": _kym_rows(rep["new_memes"], "최근 48시간에 등록된 엔트리가 없습니다."),
              "04": _threads_html(rep), "05": _reddit_html(rep), "06": _youtube_html(rep), "07": _search_wiki_html(rep),
              "08": _imgflip_html(rep), "09": _cross_html(rep), "10": _status_html(rep)}
    secs = "".join(f'<section id="s{no}"><h2><span class="no">{no}</span>{esc(t)}' + (f' <small style="color:var(--ink-2);font-weight:500">{esc(sub)}</small>' if sub else "") + f"</h2>{bodies[no]}</section>" for no, t, sub in SECTIONS)
    toc = "".join(f'<a href="#s{no}"><b>{no}</b>{esc(t)}</a>' for no, t, _ in SECTIONS)
    status = "".join(f"<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>" for k, v in rep["status"] if v not in (None, "", "—"))
    basis = "".join(f"<li>{esc(x)}</li>" for x in rep["basis_line"].split(" · "))
    return f"""<!doctype html>
<html lang="ko" data-theme="dark"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{esc(TITLE)} · {esc(rep['date'])}</title>
{ui.font_links()}
<style>{render.daily_css("media")}{MEDIA_CSS}</style></head>
<body class="media"><div class="wrap">
<div class="appbar"><div style="display:flex;align-items:center;gap:var(--sp-lg);height:100%"><span class="brand">Indie Trending</span><nav><a href="../steam/{rep['date']}.html">Steam</a><a href="../itch/{rep['date']}.html">itch.io</a><a class="on" href="#">Media</a></nav></div><span class="when">{esc(date_ko(rep['date']))} · {rep['round']}회차</span></div>
<header class="rh"><div class="hrow"><div class="l"><span class="ptag">{esc(TAG)}</span><span class="seclabel">Daily Media Report</span></div><div class="r"><span class="when">{esc(rep['date'])}</span><span class="lchip ghost">Edition #{rep['round']:02d}</span></div></div>
<h1>{esc(TITLE)} · {date_ko(rep['date'])}</h1>
<ul class="basis">{basis}</ul><dl class="status">{status}</dl></header>
<nav class="toc">{toc}</nav>
<div class="top">{_pick_html(rep.get("pick"), rep)}{_side_html(rep)}</div>
{_insight_html(rep)}
{secs}
<footer class="pf">{esc(rep['collect_line'])} · 생성 {datetime.now().strftime('%Y-%m-%d %H:%M')}<br>KYM·Reddit 제목과 About 은 원문 그대로입니다. 한국어 설명과 인사이트는 Claude 가 About 을 바탕으로 쓴 글이라 틀릴 수 있습니다. 검색량은 Google 트렌드의 대략값입니다.</footer>
</div></body></html>"""


# ====================================================================
# 이미지 카드 (1080×1350 × 2장, tokens.json 틀)
# ====================================================================

MEDIA_CARD_CSS = """
.hero{height:360px}
.cardframe{gap:20px}
.split{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:16px;align-items:stretch}
.sumbox{background:var(--surface);border:var(--bw) solid var(--line);padding:20px;display:flex;flex-direction:column;gap:8px;min-width:0}
.sumbox p{margin:0;font:var(--t-body-lg-w) var(--t-body-lg) var(--font-body);color:var(--ink);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.sumbox p.idea{color:var(--primary-light);-webkit-line-clamp:2;font:var(--t-body-md-w) var(--t-body-md) var(--font-body)}
.sumbox .when{font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);color:var(--ink-2);margin-top:auto}
.dbox{background:var(--surface);border:var(--bw) solid var(--line);padding:16px 20px;display:flex;flex-direction:column;gap:6px}
.list{background:var(--surface);border:var(--bw) solid var(--line);padding:4px 20px}
.ln{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:14px;align-items:center;padding:8px 0;border-top:var(--bw) solid var(--line)}
.ln:first-child{border-top:0}
.ln .t{font:600 var(--t-body-lg) var(--font-body);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:var(--ink)}
.ln .s{font:var(--t-data-md-w) var(--t-data-md) var(--font-mono);color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}
.ln .v{font:700 var(--t-data-md) var(--font-mono);color:var(--ink-2);white-space:nowrap}
.ln img{width:64px;height:64px;object-fit:cover;border:var(--bw) solid var(--line);background:var(--surface-2);display:block}
.ln img.yt{width:88px;height:50px}
.memes{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px}
.meme{background:var(--surface);border:var(--bw) solid var(--line);min-width:0;display:flex;flex-direction:column}
.meme .im{width:100%;aspect-ratio:1;object-fit:cover;background:var(--surface-2);display:block;border-bottom:var(--bw) solid var(--line)}
.meme .im.ph{display:flex;align-items:center;justify-content:center;font:700 40px var(--font-display);color:var(--ph-ink);background:hsl(var(--h,260) var(--ph-s) var(--ph-l))}
.meme .t{padding:8px 10px 2px;font:600 var(--t-body-md) var(--font-body);line-height:1.3;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;color:var(--ink)}
.meme .s{padding:0 10px 8px;font:var(--t-label-caps-w) var(--t-label-caps) var(--font-mono);letter-spacing:var(--t-label-caps-ls);text-transform:uppercase;color:var(--ink-2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sec{display:flex;flex-direction:column;gap:8px}
"""


def _card(rep, body, i, n, link):
    return render.card_page("media", TAG, "Media Report", f"{date_ko(rep['date'])} · {rep['round']}회차", rep["round"], body, i, n, link,
                            fallback_see=f"{TITLE} · {date_ko(rep['date'])}", extra_css=MEDIA_CARD_CSS, title=f"{TITLE} {rep['date']}")


def _title_block(kick, sub, title_html):
    return f'<div class="cardtitle"><div class="kick"><span class="lchip pos">{esc(kick)}</span><span class="seclabel">{esc(sub)}</span></div><h1 class="hl">{title_html}</h1></div>'


def _cover_card(rep):
    p = rep.get("pick")
    w = ui.tokens()["카드"]["폭"] - 2 * ui.tokens()["간격"]["카드_여백"]
    pc = list(rep["platform_counts"])
    parts = pc[:2] + ([("기타", sum(n for _, n in pc[2:]))] if len(pc) > 2 else [])
    donut = charts.donut(parts, width=int((w - 16) * (1 / 2.3)) - 40, height=170, scale="card", center_label="KYM 건", title="플랫폼 집계")
    y = (rep.get("youtube") or {}).get("KR") or {}
    yt = "".join(f'<div class="ln"><img class="yt" src="{H.escape(v.get("thumb", ""), quote=True)}" alt=""><div><div class="t">{esc(v["title"])}</div><div class="s">{esc(v["channel"])}' + (" · 쇼츠" if v.get("shorts") else "") + f'</div></div><span class="v">{esc(_views(v["views"]))}</span></div>'
                 for v in (y.get("items") or [])[:3]) if y.get("status") == "ok" else '<div class="ln"><div class="s">YOUTUBE_API_KEY 없음 · 건너뜀</div></div>'
    if p:
        streak = f"{p['streak']}일 연속" if p.get("streak", 1) > 1 else "오늘"
        chips = [f'<span class="lchip">{esc(a)}</span>' for a in (p.get("platforms") or [])[:2]] + [f'<span class="lchip ghost">{esc(f)}</span>' for f in _flags(p)[:1]]
        hero = render.image_hero_html(p.get("image"), f'<span class="ov tl">{"".join(chips)}</span>', name=p["title"])
        # RSS summary 는 원문에서 잘린 조각이라 About(전문) → summary 순으로 쓰고 문장 경계에서 끊습니다.
        summary = esc(p["ko_what"]) if p.get("ko_what") else esc(_sum(p.get("about") or p.get("summary"), 230))
        idea = f'<p class="idea">→ 활용: {esc(p["ko_idea"])}</p>' if p.get("ko_idea") else ""
        head = _title_block("TODAY'S TREND", f"KYM · {streak} · {p.get('reason', '')}", headline.to_html(headline.media_pick(p)))
        mid = (f'<div class="split"><div class="sumbox"><p>{summary}</p>{idea}<div class="when">KYM {esc(_kinds_ko(p))} · {esc(_kst(_when(p)))} KST</div></div>'
               f'<div class="dbox"><p class="seclabel">플랫폼 집계 · KYM {len(rep["kym_all"])}건 · 신규 {rep["kym_new"]}</p>{donut}</div></div>')
    else:
        head = _title_block("TODAY'S TREND", "KYM 항목 없음", "최근 48시간 틱톡·인스타 트렌드가 없습니다")
        hero = ""
        mid = f'<div class="dbox"><p class="seclabel">플랫폼 집계 · KYM {len(rep["kym_all"])}건</p>{donut}</div>'
    rl = rep.get("reels") or {}
    reels = ""
    if rl.get("status") == "ok" and rl.get("items"):
        chips = "".join(f'<span class="lchip{"" if x.get("new") else " ghost"}">{esc(x["term"][:28])} · {x["n"]}채널</span>' for x in rl["items"][:3])
        reels = f'<div class="sec"><p class="seclabel">릴스·틱톡 트렌드 Top 3 · 유튜브 정리 영상 {rl["n_videos"]}개</p><div class="terms" style="display:flex;flex-wrap:wrap;gap:8px">{chips}</div></div>'
    body = head + hero + mid + reels + f'<div class="sec"><p class="seclabel">YouTube KR 인기 급상승 Top 3</p><div class="list">{yt}</div></div>'
    return body


def _second_card(rep):
    memes = rep["new_memes"][:5]
    label = "새로 등록된 밈 · KYM 확정·제출"
    if not memes:
        memes = rep["shortform"][:5]
        label = "새 엔트리 없음 · 대신 틱톡·인스타 트렌드"
    tiles = "".join((f'<div class="meme">' + (f'<img class="im" src="{H.escape(x["image"], quote=True)}" alt="">' if x.get("image") else f'<div class="im ph" style="--h:{render.hue(x["title"])}">{esc(x["title"][:1].upper())}</div>')
                     + f'<div class="t">{esc(x["title"])}</div><div class="s">{esc(" · ".join((_flags(x)[:1]) + (x.get("platforms") or [])[:1]) or _kinds_ko(x))}</div></div>') for x in memes) \
        or '<p class="empty">없음</p>'
    im = rep["imgflip"]
    movers = im["movers"][:5] if im.get("compared") else []
    rows = "".join(f'<div class="ln"><span class="rank{" top" if x["rank"] <= 3 else ""}">{x["rank"]:02d}</span><div><div class="t">{esc(x["name"])}</div><div class="s">{x["prev_rank"]}→{x["rank"]}위 · 캡션 {(x.get("captions") or 0):,}</div></div>'
                   f'<span class="delta {"up" if (x["delta"] or 0) > 0 else "down"}">{"▲ +" if (x["delta"] or 0) > 0 else "▼ "}{x["delta"]}</span></div>' for x in movers)
    if not rows:
        rows = "".join(f'<div class="ln"><span class="rank{" top" if x["rank"] <= 3 else ""}">{x["rank"]:02d}</span><div><div class="t">{esc(x["name"])}</div><div class="s">캡션 {(x.get("captions") or 0):,}' + (" · 신규" if x.get("new") else " · 변동 없음") + '</div></div><span class="delta">—</span></div>' for x in im["items"][:5])
    cross = rep["cross"][:3]
    xs = "".join(f'<div class="ln"><div><div class="t">{esc(c["game"])} ← {esc(c["term"])}</div><div class="s">{"Steam" if c["platform"] == "steam" else "itch.io"} · {esc(c["source"])}</div></div><span class="lchip ghost">{"STEAM" if c["platform"] == "steam" else "ITCH"}</span></div>' for c in cross) \
        or '<div class="ln"><div class="s">오늘은 검색·위키·Reddit·유튜브·KYM 제목과 겹치는 게임이 없습니다.</div></div>'
    head = _title_block("NEW MEMES", f"새 밈 {len(rep['new_memes'])} · 템플릿 변동 {len(im.get('movers') or [])} · 게임 교차 {len(rep['cross'])}", "새 밈 · 템플릿 순위 · 게임 교차")
    return (head + f'<div class="sec"><p class="seclabel">{esc(label)}</p><div class="memes">{tiles}</div></div>'
            f'<div class="sec"><p class="seclabel">밈 템플릿 순위 변동 Top 5 · Imgflip{"" if im.get("compared") else " · 비교 대상 없음(회차 1)"}</p><div class="list">{rows}</div></div>'
            f'<div class="sec"><p class="seclabel">게임 ↔ 밈 교차</p><div class="list">{xs}</div></div>')


def _threads_card(rep):
    th = rep["threads"]
    w = ui.tokens()["카드"]["폭"] - 2 * ui.tokens()["간격"]["카드_여백"]
    chart = charts.bar_lift(_th_rows(th, 8), width=w, height=470, scale="card", max_rows=8, label_chars=12, title="Threads 키워드별 24시간 게시 수")
    terms = "".join(f'<span class="lchip{" pos" if (t.get("delta") or 0) >= 3 else " ghost"}">{esc(t["term"])}</span>' for t in (th.get("rising") or [])[:10]) or '<span class="lchip ghost">아직 없음</span>'
    samples = "".join(f'<div class="ln"><div><div class="t">{esc(sp["text"])}</div><div class="s">{esc(sp["keyword"])} · @{esc(sp["username"])}</div></div><span class="v">{"TOP" if sp.get("from") == "top" else "NEW"}</span></div>'
                      for sp in _th_samples(th, 5)) or '<div class="ln"><div class="s">본문이 있는 글이 없습니다.</div></div>'
    top = th["keywords"][0] if th["keywords"] else None
    sub = f"키워드 {th['n_ok']}개 · 글 {th['total_posts']}건" + (" · 전날 대비" if th.get("compared") else " · 첫 회차")
    title = (f'<span class="hi">{esc(top["keyword"])}</span> 24시간 {esc(_th_count(top))}건'
             + (f' <span style="color:var(--{"rise" if top["delta"] > 0 else "fall"})">{esc(_th_delta(top))}</span>' if top.get("delta") else "")) if top else "오늘 수집한 글이 없습니다"
    head = _title_block("THREADS", sub, title)
    return (head + f'<div class="sec"><p class="seclabel">24시간 게시 수 Top 8 · 초록 = 전날의 1.5배 이상</p><div class="dbox">{chart}</div></div>'
            f'<div class="sec"><p class="seclabel">새로 뜨는 말</p><div class="terms" style="display:flex;flex-wrap:wrap;gap:8px">{terms}</div></div>'
            f'<div class="sec"><p class="seclabel">대표 글</p><div class="list">{samples}</div></div>')


def to_cards(rep, link=None):
    pages = [_cover_card(rep), _second_card(rep)]
    if (rep.get("threads") or {}).get("status") == "ok" and rep["threads"].get("keywords"):
        pages.append(_threads_card(rep))
    return [(f"{rep['date']}-{i}.png", _card(rep, body, i, len(pages), link)) for i, body in enumerate(pages, 1)]


# ====================================================================
# Discord 임베드
# ====================================================================

def build_embeds(rep, link, clip, limits):
    """clip(s, n) 과 limits(dict: title, desc, field_name, field, footer, total) 는 notify.py 의 것을 넘깁니다."""
    LT, LD, LFN, LF, LFT, LTOT = (limits[k] for k in ("title", "desc", "field_name", "field", "footer", "total"))
    embeds = []
    p = rep.get("pick")
    llm = has_llm(rep)

    def link_md(x, n=70):
        t = x["title"] if len(x["title"]) <= n else x["title"][: n - 1].rstrip() + "…"
        return f"[{_mdsafe(t)}]({x['url']})"

    def tags(x, n=2):
        return " · ".join((x.get("platforms") or [])[:n])

    def item_md(x, with_flags=False):
        head = f"• {link_md(x)}" + ("".join(f" · {f}" for f in _flags(x)[:1]) if with_flags else "") + (f" · {tags(x)}" if tags(x) else "")
        if x.get("ko_what"):
            head += f"\n-# {_mdsafe(x['ko_what'])}"
        if x.get("ko_idea"):
            head += f"\n-# → 활용: {_mdsafe(x['ko_idea'])}"
        return head

    # 1. 표지
    cover = {"title": clip(f"{TITLE} · {date_ko(rep['date'])} · {rep['round']}회차", LT), "color": COLOR}
    if link:
        cover["url"] = link
    lines = []
    if p:
        streak = f" · {p['streak']}일 연속" if p.get("streak", 1) > 1 else ""
        lines.append(f"**오늘의 트렌드 → {link_md(p)}**{streak}")
        lines.append(_mdsafe(p["ko_what"]) if p.get("ko_what") else _sum(p.get("summary", "")))
        if p.get("ko_idea"):
            lines.append(f"→ 활용: {_mdsafe(p['ko_idea'])}")
        lines.append(" · ".join([tags(p, 3)] + _flags(p)[:2]).strip(" ·"))
        if p.get("image"):
            cover["image"] = {"url": p["image"]}
    else:
        lines.append("최근 48시간 KYM 항목이 없습니다.")
    pc = " · ".join(f"{a} {n}건" for a, n in rep["platform_counts"]) or "플랫폼 단서 없음"
    lines.append(f"\n**플랫폼 집계** KYM {len(rep['kym_all'])}건 (신규 {rep['kym_new']}) · {pc}")
    others = [x for x in rep["shortform"] if not p or x["url"] != p["url"]][: (2 if llm else 3)]
    if others:
        lines.append("\n**다른 틱톡·인스타 트렌드**\n" + "\n".join(item_md(x) for x in others))
    if rep.get("insight"):
        lines.append(f"\n**오늘의 인사이트**\n{_mdsafe(rep['insight'])}")
    cover["description"] = clip("\n".join(lines), LD)
    embeds.append(cover)

    # 1-1. 릴스·틱톡 트렌드 정리 (YouTube 키 있을 때만 임베드, 없으면 마지막 임베드에 메모 한 줄)
    rl = rep.get("reels") or {}
    if rl.get("status") == "ok" and (rl.get("items") or rl.get("videos")):
        rlines = ["**트렌드 항목 Top 8** " + (_rl_term_line(rl, 8, md=True) or "없음")]
        if rl.get("videos"):
            rlines.append("**정리 영상 Top 5**\n" + "\n".join(f"• {link_md(v, 50)} · {_mdsafe(v['channel'][:20])} · {_views(v['views'])}" + (" · NEW" if v.get("new") else "") for v in rl["videos"][:5]))
        embeds.append({"title": clip(f"릴스·틱톡 트렌드 정리 · 유튜브 정리 영상 {rl['n_videos']}개 · 항목 {rl['n_items']}" + (" · 전날 대비" if rl.get("compared") else ""), LT),
                       "color": 0xE1306C, "description": clip("\n".join(rlines), LD)})

    # 2. 새로 등록된 밈
    memes = rep["new_memes"][: (4 if llm else 5)]
    body = "\n".join(item_md(x, with_flags=True) for x in memes) or "• 최근 48시간 새 엔트리 없음"
    embeds.append({"title": f"새로 등록된 밈 · KYM {len(rep['new_memes'])}건", "color": COLOR, "description": clip(body, LD)})

    # 3. Threads 키워드 관찰 (토큰 있을 때만 임베드, 없으면 마지막 임베드에 메모 한 줄)
    th = rep.get("threads") or {}
    if th.get("status") == "ok" and th.get("keywords"):
        tl = ["**24시간 게시 수** " + " · ".join(f"{_mdsafe(x['keyword'])} {_th_count(x)}" + (f" {_th_delta(x)}" if _th_delta(x) else "") for x in th["keywords"][:8])]
        if th.get("rising"):
            tl.append("**새로 뜨는 말** " + _th_term_line(th, 8, md=True))
        sp = _th_samples(th, 3)
        if sp:
            tl.append("**대표 글**\n" + "\n".join(f"• [{_mdsafe(x['keyword'])}] @{_mdsafe(x['username'])}: [{_mdsafe(x['text'][:90])}]({x['url']})" for x in sp))
        if th.get("note"):
            tl.append(f"-# {_note_md(th['note'])}")
        embeds.append({"title": clip(f"Threads 키워드 관찰 · {th['n_ok']}개 키워드 · 글 {th['total_posts']}건" + (" · 전날 대비" if th.get("compared") else ""), LT),
                       "color": 0x101010, "description": clip("\n".join(tl), LD)})

    # 4. 커뮤니티 베스트
    rd = [f"• r/{r['sub']} {link_md(r['items'][0])}" for r in rep["reddit"] if r["status"] == "ok" and r["items"]]
    fails = [f"r/{r['sub']}" for r in rep["reddit"] if r["status"] != "ok"]
    desc = "\n".join(rd) or "Reddit 수집 실패"
    if fails:
        desc += f"\n(실패: {', '.join(fails)})"
    embeds.append({"title": "커뮤니티 베스트 · Reddit", "color": COLOR, "description": clip(desc, LD)})

    # 5. 유튜브 인기 급상승 (키 있을 때만)
    yt_fields = []
    for region in ("KR", "US"):
        y = rep["youtube"][region]
        if y["status"] == "ok":
            val = "\n".join(f"**{v['rank']}.** {link_md(v, 40)} · {_views(v['views'])}" + (" · 쇼츠" if v.get("shorts") else "") for v in y["items"][:5]) or "항목 없음"
            yt_fields.append({"name": clip(f"{region} Top 5 (쇼츠 {y['shorts']}/{y['total']})", LFN), "value": clip(val, LF), "inline": True})
    if yt_fields:
        embeds.append({"title": "유튜브 인기 급상승", "color": 0xB4261D, "fields": yt_fields})

    # 6. 검색·위키 한 줄 + 밈 템플릿 + 게임 교차 + 상세 링크
    f = rep["filtered"]
    tail = []
    for geo in ("KR", "US"):
        tail.append(f"**검색 {geo}** " + (" · ".join(f"{link_md(x)} {_fmt_traffic(x)}" for x in rep["trends"][geo][:3]) or "없음") + (f" (제외 {f.get('trends_' + geo.lower(), 0)})" if f.get("trends_" + geo.lower()) else ""))
    for proj in ("en", "ko"):
        tail.append(f"**위키 {proj}** " + (" · ".join(link_md(x) for x in rep["wiki"][proj][:3]) or "없음") + (f" (제외 {f.get('wiki_' + proj, 0)})" if f.get("wiki_" + proj) else ""))
    im = rep["imgflip"]
    if im["compared"]:
        mv = ", ".join(f"{_mdsafe(x['name'])} {x['prev_rank']}→{x['rank']}위" for x in im["movers"][:3]) or "상위 30 변동 없음"
        tail.append(f"**밈 템플릿** {mv} · 신규 {len(im['entered'])} · 이탈 {len(im['exited'])}")
    else:
        tail.append("**밈 템플릿** 비교 대상 없음 (회차 1)")
    if rep["cross"]:
        tail.append(f"**게임 교차 {len(rep['cross'])}건** " + " · ".join(f"{_mdsafe(c['term'][:40])} → [{_mdsafe(c['game'])}]({c['game_url']})" for c in rep["cross"][:3]))
    else:
        tail.append("**게임 교차** 없음")
    if th.get("status") != "ok" and th.get("note"):
        tail.append(f"-# {_note_md(th['note'])}")
    if rl.get("status") != "ok" and rl.get("note"):
        tail.append(f"-# {_note_md(rl['note'])}")
    if link:
        tail.append(f"\n**[📄 상세 보고서 열기]({link})**")
    embeds.append({"title": "검색 · 위키 · 밈 템플릿 · 게임 교차", "color": 0x33409E, "description": clip("\n".join(tail), LD),
                   "footer": {"text": clip(rep["collect_line"], LFT)}})

    def elen(e):
        return len(e.get("title", "")) + len(e.get("description", "")) + len((e.get("footer") or {}).get("text", "")) + sum(len(x["name"]) + len(x["value"]) for x in e.get("fields", []))

    while len(embeds) > 10:     # 임베드 10개 제한: 넘치면 마지막(검색·위키) 임베드에 바로 앞 임베드를 합칩니다
        extra = embeds.pop(-2)
        last = embeds[-1]
        last["description"] = clip(f"**{extra.get('title', '')}**\n{extra.get('description', '')}\n\n{last.get('description', '')}", LD)

    # 합 6000자 초과분은 상세 링크·footer 가 든 마지막 임베드를 맨 나중에, 그 앞 임베드들은 뒤에서부터 줄입니다.
    excess = sum(elen(e) for e in embeds) - LTOT
    for e in list(reversed(embeds[:-1])) + embeds[-1:]:
        if excess <= 0:
            break
        d = e.get("description", "")
        if len(d) > 80:
            cut = min(len(d) - 80, excess)
            e["description"] = clip(d, len(d) - cut)
            excess -= cut
    return embeds
