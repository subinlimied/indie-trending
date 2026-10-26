"""외부 라이브러리 없이 SVG 문자열을 만드는 차트 세 가지.

색은 CSS 변수(--rise, --accent, --ink …)로 넣어 HTML 에서는 라이트·다크가 자동으로 바뀌고,
카드(다크 고정)에서는 ui.css_vars(mode="dark") 가 같은 변수를 채웁니다.
글자 크기·선 두께는 design/tokens.json 의 '카드'·'웹' 단계에서 읽습니다(scale 인자).

    from market import charts
    charts.sparkline([30, 22, None, 15, 12], width=936, height=120, scale="card")
    charts.bump_chart({"A": [3,2,1,1,1,1,1], ...}, days=["10-20",...], highlight="A", secondary=["B"], width=936, height=760, scale="card")
    charts.bar_lift([("Simulation", 13, 1.4), ...], width=936, height=700, scale="card")
"""
import html as H

from . import ui


def _f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _trunc(s, n):
    s = s or ""
    return s if len(s) <= n else s[: max(1, n - 1)].rstrip() + "…"


def _segments(values):
    """None 으로 끊긴 연속 구간들을 [(i, v), ...] 목록으로."""
    segs, cur = [], []
    for i, v in enumerate(values):
        if v is None:
            if cur:
                segs.append(cur)
            cur = []
        else:
            cur.append((i, v))
    if cur:
        segs.append(cur)
    return segs


# ---------- 스파크라인 ----------

def sparkline(values, width=300, height=60, scale="web", invert=True, highlight_last=True, labels=None, color=None, title=""):
    """values: 숫자 또는 None 목록(왼쪽이 과거). invert=True 면 작은 값(1위)이 위.
    None 은 선을 끊습니다. labels 를 주면(같은 길이, 'MM-DD') 양 끝 아래에 날짜를 적습니다."""
    t = ui.chart_theme(scale)
    col = color or t["accent"]
    pad_x = t["dot"] * 2 + 2
    fs = t["fs_axis"]
    lab_h = fs * 1.5 if labels else 0
    pad_top = t["dot"] * 2 + (fs * 1.3 if highlight_last else 2)
    pad_bot = t["dot"] * 2 + 2 + lab_h
    nums = [v for v in values if v is not None]
    n = len(values)
    out = [f'<svg class="chart spark" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{H.escape(title, quote=True)}">']
    if not nums or n == 0:
        out.append(f'<text x="{width / 2}" y="{height / 2}" dy=".35em" text-anchor="middle" class="tx" style="font-size:{fs}px;fill:{t["ink3"]}">데이터 없음</text></svg>')
        return "".join(out)
    lo, hi = min(nums), max(nums)
    if lo == hi:
        lo, hi = lo - 1, hi + 1
    plot_h = height - pad_top - pad_bot
    step = (width - pad_x * 2) / max(n - 1, 1)

    def X(i):
        return pad_x + i * step

    def Y(v):
        r = (v - lo) / (hi - lo)
        return pad_top + (r if invert else 1 - r) * plot_h

    # 바탕 기준선(가장 좋은 값 위치) — 얇게
    out.append(f'<line x1="{pad_x}" x2="{width - pad_x}" y1="{Y(lo if invert else hi):.1f}" y2="{Y(lo if invert else hi):.1f}" style="stroke:{t["line_c"]};stroke-width:1"/>')
    for seg in _segments(values):
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in seg)
        if len(seg) > 1:
            # 면: 선 아래(순위면 선 아래가 '더 나쁜 쪽')를 10% 로
            base = pad_top + plot_h
            area = f"M{X(seg[0][0]):.1f},{base:.1f} L" + " L".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in seg) + f" L{X(seg[-1][0]):.1f},{base:.1f} Z"
            out.append(f'<path d="{area}" style="fill:{col};opacity:.12"/>')
            out.append(f'<polyline points="{pts}" style="fill:none;stroke:{col};stroke-width:{t["line"]};stroke-linejoin:round;stroke-linecap:round"/>')
            for i, v in seg:
                out.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="{t["dot"] * .55}" style="fill:{col}"/>')
        else:
            i, v = seg[0]
            out.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="{t["dot"] * .8}" style="fill:{col}"/>')
    # 마지막 점 강조
    last_i = max((i for i, v in enumerate(values) if v is not None), default=None)
    if highlight_last and last_i is not None:
        v = values[last_i]
        out.append(f'<circle cx="{X(last_i):.1f}" cy="{Y(v):.1f}" r="{t["dot"] * 1.6}" style="fill:{t["surface"]}"/>'
                   f'<circle cx="{X(last_i):.1f}" cy="{Y(v):.1f}" r="{t["dot"]}" style="fill:{col}"/>')
        anchor = "end" if last_i > n / 2 else "start"
        dx = -t["dot"] * 2 if anchor == "end" else t["dot"] * 2
        out.append(f'<text x="{X(last_i) + dx:.1f}" y="{Y(v) - t["dot"] * 1.6 - 2:.1f}" text-anchor="{anchor}" style="font-size:{fs}px;font-weight:700;fill:{t["ink"]}">{_f(v)}{"위" if invert else ""}</text>')
    if labels and len(labels) == n:
        y = height - 2
        out.append(f'<text x="{pad_x}" y="{y}" text-anchor="start" style="font-size:{fs}px;fill:{t["ink3"]}">{H.escape(labels[0])}</text>')
        if n > 1:
            out.append(f'<text x="{width - pad_x}" y="{y}" text-anchor="end" style="font-size:{fs}px;fill:{t["ink3"]}">{H.escape(labels[-1])}</text>')
    out.append("</svg>")
    return "".join(out)


# ---------- 범프 차트 ----------

def bump_chart(series, days, highlight=None, secondary=(), width=936, height=760, scale="web", n=10, label_chars=18, title=""):
    """series: {이름: [순위|None] × len(days)}. 1~n 행 + 'n 밖' 행(순위가 n 보다 크면 거기에 둠).
    highlight(이름 또는 이름 목록)는 상승 초록·굵게, secondary 는 중간 회색, 나머지는 옅게.
    오른쪽 끝에 이름 라벨(오늘 순위 순). 겹치면 위아래로 밀어 냅니다."""
    t = ui.chart_theme(scale)
    fs, fl = t["fs_axis"], t["fs_label"]
    hi = set([highlight] if isinstance(highlight, str) else (highlight or []))
    sec = set(secondary or []) - hi
    cols = len(days)
    # 라벨 폭: 글자 수 × 글자 크기 × 0.55 (본문 서체 기준 대략값)
    label_w = int(label_chars * fl * 0.58) + fs
    pad_l = fs * 3.2
    pad_t = fs * 2.2
    pad_b = fs * 1.2
    rows = n + 1  # 마지막 행 = n 밖
    plot_w = width - pad_l - label_w - t["dot"] * 2
    plot_h = height - pad_t - pad_b
    row_h = plot_h / rows
    col_w = plot_w / max(cols - 1, 1)

    def X(i):
        return pad_l + i * col_w

    def Y(r):
        rr = min(r, n + 1)
        return pad_t + (rr - .5) * row_h

    out = [f'<svg class="chart bump" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{H.escape(title, quote=True)}">']
    # 행 안내선 + 왼쪽 축
    for r in range(1, rows + 1):
        y = Y(r)
        out.append(f'<line x1="{pad_l}" x2="{pad_l + plot_w:.1f}" y1="{y:.1f}" y2="{y:.1f}" style="stroke:{t["line_c"]};stroke-width:1"/>')
        lab = str(r) if r <= n else f"{n}밖"
        out.append(f'<text x="{pad_l - fs * .6:.1f}" y="{y:.1f}" dy=".35em" text-anchor="end" style="font-size:{fs}px;fill:{t["ink3"]}">{lab}</text>')
    # 위 축(날짜)
    for i, d in enumerate(days):
        out.append(f'<text x="{X(i):.1f}" y="{pad_t - fs * .8:.1f}" text-anchor="middle" style="font-size:{fs}px;fill:{t["ink3"]}">{H.escape(d)}</text>')
        out.append(f'<line x1="{X(i):.1f}" x2="{X(i):.1f}" y1="{pad_t}" y2="{pad_t + plot_h:.1f}" style="stroke:{t["line_c"]};stroke-width:1;opacity:.6"/>')
    # 선: 옅은 것 → 중간 → 강조 순서로 그려 강조가 맨 위에 오게
    order = sorted(series.items(), key=lambda kv: (2 if kv[0] in hi else 1 if kv[0] in sec else 0))
    for name, vals in order:
        vals = list(vals)[:cols] + [None] * max(0, cols - len(vals))
        if name in hi:
            col, w, op, dot = t["rise"], t["line_hi"], 1, t["dot"] * 1.2
        elif name in sec:
            col, w, op, dot = t["ink2"], t["line"] * 1.2, .95, t["dot"]
        else:
            col, w, op, dot = t["line_strong"], t["line"], .9, t["dot"] * .8
        for seg in _segments(vals):
            if len(seg) > 1:
                pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in seg)
                out.append(f'<polyline points="{pts}" style="fill:none;stroke:{col};stroke-width:{w};stroke-linejoin:round;stroke-linecap:round;opacity:{op}"/>')
            for i, v in seg:
                out.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="{dot + 2}" style="fill:{t["surface"]}"/>'
                           f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="{dot}" style="fill:{col};opacity:{op}"/>')
    # 오른쪽 라벨: 마지막 값 기준, 겹치면 밀어 냄
    labels = []
    for name, vals in series.items():
        vals = list(vals)[:cols]
        last = next((v for v in reversed(vals) if v is not None), None)
        if last is None:
            continue
        labels.append([Y(last), name, last])
    labels.sort()
    min_gap = fl * 1.25
    for k in range(1, len(labels)):
        if labels[k][0] - labels[k - 1][0] < min_gap:
            labels[k][0] = labels[k - 1][0] + min_gap
    # 아래로 넘치면 전체를 위로 끌어올림
    if labels and labels[-1][0] > pad_t + plot_h:
        shift = labels[-1][0] - (pad_t + plot_h)
        for lb in labels:
            lb[0] -= shift
        for k in range(len(labels) - 2, -1, -1):
            if labels[k + 1][0] - labels[k][0] < min_gap:
                labels[k][0] = labels[k + 1][0] - min_gap
    lx = pad_l + plot_w + t["dot"] * 2 + fs * .4
    for y, name, last in labels:
        if name in hi:
            style = f"font-size:{fl}px;font-weight:700;fill:{t['ink']}"
        elif name in sec:
            style = f"font-size:{fl}px;font-weight:600;fill:{t['ink2']}"
        else:
            style = f"font-size:{fl}px;fill:{t['ink3']}"
        out.append(f'<text class="tx" x="{lx:.1f}" y="{y:.1f}" dy=".35em" style="{style}"><title>{H.escape(name)} · {last}위</title>{H.escape(_trunc(name, label_chars))}</text>')
    out.append("</svg>")
    return "".join(out)


# ---------- 소재·장르 막대 ----------

def bar_lift(rows, width=936, height=600, scale="web", hot=1.5, max_rows=8, label_chars=16, title=""):
    """rows: [(태그, 개수, 배율|None)]. 가로 막대(개수) + 막대 끝에 배율 점·숫자. 배율 >= hot 는 강조색."""
    t = ui.chart_theme(scale)
    fs, fl = t["fs_axis"], t["fs_label"]
    rows = list(rows)[:max_rows]
    out = [f'<svg class="chart lift" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{H.escape(title, quote=True)}">']
    if not rows:
        out.append(f'<text x="{width / 2}" y="{height / 2}" class="tx" text-anchor="middle" style="font-size:{fl}px;fill:{t["ink3"]}">데이터 없음</text></svg>')
        return "".join(out)
    label_w = int(label_chars * fl * .58)
    mult_w = fl * 4.2  # "1.5×" + 여백
    pad_l = label_w + fl * .8
    bar_h = min(fl * 1.5, (height / len(rows)) * .55)
    row_h = height / len(rows)
    plot_w = width - pad_l - mult_w - t["dot"] * 3
    mx = max((c for _, c, _ in rows), default=1) or 1
    for k, (tag, cnt, mult) in enumerate(rows):
        cy = (k + .5) * row_h
        is_hot = mult is not None and mult >= hot
        col = t["rise"] if is_hot else t["accent"]
        w = max(plot_w * cnt / mx, 2)
        y0 = cy - bar_h / 2
        # 막대: 끝만 둥글게 (왼쪽 기준선은 각지게) — path 로 그립니다
        r = min(bar_h / 2, 6 if scale == "web" else 10)
        d = f"M{pad_l:.1f},{y0:.1f} H{pad_l + w - r:.1f} a{r},{r} 0 0 1 {r},{r} V{y0 + bar_h - r:.1f} a{r},{r} 0 0 1 -{r},{r} H{pad_l:.1f} Z"
        out.append(f'<path d="{d}" style="fill:{col};opacity:{1 if is_hot else .55}"><title>{H.escape(tag)} · {cnt}개 · {_f(mult) if mult is not None else "—"}×</title></path>')
        # 태그 이름
        out.append(f'<text class="tx" x="{pad_l - fl * .8:.1f}" y="{cy:.1f}" dy=".35em" text-anchor="end" style="font-size:{fl}px;font-weight:{700 if is_hot else 500};fill:{t["ink"] if is_hot else t["ink2"]}">{H.escape(_trunc(tag, label_chars))}</text>')
        # 개수: 막대 안(충분히 길면) 또는 막대 밖
        cnt_s = f"{cnt}"
        if w > fs * 3:
            out.append(f'<text x="{pad_l + w - fs * .6:.1f}" y="{cy:.1f}" dy=".35em" text-anchor="end" style="font-size:{fs}px;font-weight:700;fill:{t["surface"] if is_hot else t["ink"]}">{cnt_s}</text>')
        else:
            out.append(f'<text x="{pad_l + w + fs * .5:.1f}" y="{cy:.1f}" dy=".35em" style="font-size:{fs}px;font-weight:700;fill:{t["ink"]}">{cnt_s}</text>')
        # 배율 점 + 숫자 (오른쪽 고정 열)
        mx_x = width - mult_w + t["dot"] * 1.5
        if mult is not None:
            out.append(f'<circle cx="{mx_x:.1f}" cy="{cy:.1f}" r="{t["dot"] * (1.4 if is_hot else 1)}" style="fill:{col}"/>')
            out.append(f'<text x="{mx_x + t["dot"] * 2.4:.1f}" y="{cy:.1f}" dy=".35em" style="font-size:{fl}px;font-weight:{700 if is_hot else 500};fill:{t["ink"] if is_hot else t["ink2"]}">{_f(mult)}×</text>')
        else:
            out.append(f'<text x="{mx_x + t["dot"] * 2.4:.1f}" y="{cy:.1f}" dy=".35em" style="font-size:{fl}px;fill:{t["ink3"]}">—</text>')
    # 기준선
    out.append(f'<line x1="{pad_l:.1f}" x2="{pad_l:.1f}" y1="0" y2="{height}" style="stroke:{t["line_strong"]};stroke-width:1"/>')
    out.append("</svg>")
    return "".join(out)
