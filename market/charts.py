"""외부 라이브러리 없이 SVG 문자열을 만드는 차트 세 가지 ('Terminal Editorial' 시안: 1px 선, 모노 라벨, 초록 강조, 반지름 0).

색은 CSS 변수(--rise, --accent, --ink …)로 넣어 ui.css_vars 가 채웁니다.
글자 크기·선 두께는 design/tokens.json 에서 읽습니다(scale 인자, 카드와 웹이 같은 값).

    from market import charts
    charts.sparkline([30, 22, None, 15, 12], width=936, height=170, labels=["D-4","D-3","D-2","D-1","TODAY"])
    charts.bump_chart({"A": [3,2,1,1,1,1,1], ...}, days=["10-20",...], highlight="A", secondary=["B"], width=936, height=700)
    charts.bar_lift([("Simulation", 13, 1.4), ...], width=936, height=600)
"""
import html as H

from . import ui


def _f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def _trunc(s, n):
    s = s or ""
    return s if len(s) <= n else s[: max(1, n - 1)].rstrip() + "…"


def _segments(values):
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

def sparkline(values, width=700, height=170, scale="web", invert=True, highlight_last=True, labels=None, color=None, title="",
              point_labels=True, unit="위", uid="sp"):
    """values: 숫자 또는 None(왼쪽이 과거). invert=True 면 작은 값(1위)이 위.
    1.5px 선, 점은 표면색 속 + 선 테두리, 마지막 점은 채움. 선 아래는 옅은 세로 그라데이션만.
    상승(마지막이 처음보다 좋음)은 초록, 하락은 산호. labels(['D-6', …, 'TODAY'])를 주면 점 아래에 값과 날짜 라벨을 두 줄로 적습니다.
    None 은 선을 끊고 라벨은 '—'."""
    t = ui.chart_theme(scale)
    fs, fl = t["fs_axis"], t["fs_label"]
    n = len(values)
    nums = [v for v in values if v is not None]
    pad_x = t["dot"] * 3
    lab_h = (fl * 1.2 + fs * 1.4 + 10) if (labels and point_labels) else 0
    pad_top = t["dot"] * 3
    pad_bot = t["dot"] * 3 + lab_h
    out = [f'<svg class="chart spark" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{H.escape(title, quote=True)}">']
    if not nums or n == 0:
        out.append(f'<text x="{width / 2}" y="{height / 2}" dy=".35em" text-anchor="middle" class="tx" style="font-size:{fl}px;fill:{t["ink3"]}">데이터 없음</text></svg>')
        return "".join(out)
    first, last = nums[0], nums[-1]
    improving = (last < first) if invert else (last > first)
    col = color or (t["rise"] if improving or last == first else t["fall"])
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

    base = pad_top + plot_h
    for y in (pad_top, pad_top + plot_h / 2, base):
        out.append(f'<line x1="{pad_x}" x2="{width - pad_x}" y1="{y:.1f}" y2="{y:.1f}" style="stroke:{t["line_c"]};stroke-width:1"/>')
    gid = f"g-{uid}"
    out.append(f'<defs><linearGradient id="{gid}" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" style="stop-color:{col};stop-opacity:.22"/><stop offset="90%" style="stop-color:{col};stop-opacity:0"/></linearGradient></defs>')
    for seg in _segments(values):
        if len(seg) > 1:
            pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in seg)
            area = f"M{X(seg[0][0]):.1f},{base:.1f} L" + " L".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in seg) + f" L{X(seg[-1][0]):.1f},{base:.1f} Z"
            out.append(f'<path d="{area}" style="fill:url(#{gid})"/>')
            out.append(f'<polyline points="{pts}" style="fill:none;stroke:{col};stroke-width:{t["line"]};stroke-linejoin:round;stroke-linecap:round"/>')
        for i, v in seg:
            out.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="{t["dot"]}" style="fill:{t["surface"]};stroke:{col};stroke-width:1.5"/>')
    last_i = max((i for i, v in enumerate(values) if v is not None), default=None)
    if highlight_last and last_i is not None:
        v = values[last_i]
        out.append(f'<circle cx="{X(last_i):.1f}" cy="{Y(v):.1f}" r="{t["dot"] * 2}" style="fill:{col};opacity:.25"/>'
                   f'<circle cx="{X(last_i):.1f}" cy="{Y(v):.1f}" r="{t["dot"] * 1.3}" style="fill:{col};stroke:{t["bg"]};stroke-width:1.5"/>')
    if labels and point_labels and len(labels) == n:
        y1 = base + 10 + fl
        y2 = y1 + fs * 1.4
        out.append(f'<line x1="{pad_x}" x2="{width - pad_x}" y1="{base + 6:.1f}" y2="{base + 6:.1f}" style="stroke:{t["line_c"]};stroke-width:1"/>')
        for i, lab in enumerate(labels):
            v = values[i]
            is_last = i == last_i
            anchor = "start" if i == 0 and n > 1 else "end" if i == n - 1 and n > 1 else "middle"
            vcol = col if is_last else t["ink"]
            out.append(f'<text x="{X(i):.1f}" y="{y1:.1f}" text-anchor="{anchor}" style="font-size:{fl}px;font-weight:700;fill:{vcol if v is not None else t["ink3"]}">{_f(v) + unit if v is not None else "목록 밖"}</text>')
            out.append(f'<text x="{X(i):.1f}" y="{y2:.1f}" text-anchor="{anchor}" style="font-size:{fs}px;font-weight:{700 if is_last else 500};letter-spacing:.06em;fill:{col if is_last else t["ink2"]}">{H.escape(lab)}</text>')
    out.append("</svg>")
    return "".join(out)


# ---------- 범프 차트 ----------

def bump_chart(series, days, highlight=None, secondary=(), width=936, height=700, scale="web", n=10, label_chars=18, title=""):
    """series: {이름: [순위|None] × len(days)}. 1~n 행 + 'n+' 행. 1px 안내선, 모노 축 라벨.
    highlight 는 초록 3px, secondary 는 글자_1 색 1.5px, 나머지는 선 색. 오른쪽 끝 이름 라벨(겹치면 밀어 냄)."""
    t = ui.chart_theme(scale)
    fs, fl = t["fs_axis"], t["fs_label"]
    hi = set([highlight] if isinstance(highlight, str) else (highlight or []))
    sec = set(secondary or []) - hi
    cols = len(days)
    label_w = int(label_chars * fl * 0.58) + fs
    pad_l = fs * 3.6
    pad_t = fs * 2.6
    pad_b = fs * 1.2
    rows = n + 1
    plot_w = width - pad_l - label_w - t["dot"] * 2
    plot_h = height - pad_t - pad_b
    row_h = plot_h / rows
    col_w = plot_w / max(cols - 1, 1)

    def X(i):
        return pad_l + i * col_w

    def Y(r):
        return pad_t + (min(r, n + 1) - .5) * row_h

    out = [f'<svg class="chart bump" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{H.escape(title, quote=True)}">']
    for r in range(1, rows + 1):
        y = Y(r)
        out.append(f'<line x1="{pad_l}" x2="{pad_l + plot_w:.1f}" y1="{y:.1f}" y2="{y:.1f}" style="stroke:{t["line_c"]};stroke-width:1"/>')
        lab = f"{r:02d}" if r <= n else f"{n}+"
        out.append(f'<text x="{pad_l - fs * .8:.1f}" y="{y:.1f}" dy=".35em" text-anchor="end" style="font-size:{fs}px;letter-spacing:.06em;fill:{t["ink2"]}">{lab}</text>')
    for i, d in enumerate(days):
        last = i == cols - 1
        out.append(f'<text x="{X(i):.1f}" y="{pad_t - fs * 1.1:.1f}" text-anchor="middle" style="font-size:{fs}px;font-weight:{700 if last else 500};letter-spacing:.06em;fill:{t["ink"] if last else t["ink2"]}">{H.escape(d)}</text>')
        out.append(f'<line x1="{X(i):.1f}" x2="{X(i):.1f}" y1="{pad_t}" y2="{pad_t + plot_h:.1f}" style="stroke:{t["line_c"]};stroke-width:1"/>')
    order = sorted(series.items(), key=lambda kv: (2 if kv[0] in hi else 1 if kv[0] in sec else 0))
    for name, vals in order:
        vals = list(vals)[:cols] + [None] * max(0, cols - len(vals))
        if name in hi:
            col, w, dot = t["rise"], t["line_hi"], t["dot"] * 1.3
        elif name in sec:
            col, w, dot = t["ink"], t["line"], t["dot"]
        else:
            col, w, dot = t["line_strong"], t["line"], t["dot"] * .8
        for seg in _segments(vals):
            if len(seg) > 1:
                pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in seg)
                out.append(f'<polyline points="{pts}" style="fill:none;stroke:{col};stroke-width:{w};stroke-linejoin:round;stroke-linecap:round"/>')
            for i, v in seg:
                out.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="{dot}" style="fill:{t["bg"]};stroke:{col};stroke-width:1.5"/>')
    labels = []
    for name, vals in series.items():
        vals = list(vals)[:cols]
        last = next((v for v in reversed(vals) if v is not None), None)
        if last is not None:
            labels.append([Y(last), name, last])
    labels.sort()
    min_gap = fl * 1.25
    for k in range(1, len(labels)):
        if labels[k][0] - labels[k - 1][0] < min_gap:
            labels[k][0] = labels[k - 1][0] + min_gap
    if labels and labels[-1][0] > pad_t + plot_h:
        shift = labels[-1][0] - (pad_t + plot_h)
        for lb in labels:
            lb[0] -= shift
        for k in range(len(labels) - 2, -1, -1):
            if labels[k + 1][0] - labels[k][0] < min_gap:
                labels[k][0] = labels[k + 1][0] - min_gap
    lx = pad_l + plot_w + t["dot"] * 2 + fs * .6
    for y, name, last in labels:
        if name in hi:
            style = f"font-size:{fl}px;font-weight:700;fill:{t['rise']}"
        elif name in sec:
            style = f"font-size:{fl}px;font-weight:600;fill:{t['ink']}"
        else:
            style = f"font-size:{fl}px;fill:{t['ink2']}"
        out.append(f'<text class="tx" x="{lx:.1f}" y="{y:.1f}" dy=".35em" style="{style}"><title>{H.escape(name)} · {last}위</title>{H.escape(_trunc(name, label_chars))}</text>')
    out.append("</svg>")
    return "".join(out)


# ---------- 소재·장르 막대 ----------

def _wrap2(s, n):
    """n 글자를 넘으면 가운데에 가까운 공백에서 두 줄로. 공백이 없으면 자릅니다."""
    if len(s) <= n:
        return [s]
    cut = None
    for i, ch in enumerate(s):
        if ch in " -/·" and abs(i - len(s) / 2) <= n / 2:
            if cut is None or abs(i - len(s) / 2) < abs(cut - len(s) / 2):
                cut = i
    if cut is None:
        return [_trunc(s, n)]
    a, b = s[:cut].rstrip(), s[cut:].lstrip(" -/·")
    return [_trunc(a, n), _trunc(b, n)]


def bar_lift(rows, width=936, height=600, scale="web", hot=1.5, max_rows=8, label_chars=16, title=""):
    """rows: [(태그, 개수, 배율|None)]. 사각 가로 막대(개수) + 오른쪽 고정 열에 배율 점·숫자. 배율 >= hot 는 초록, 나머지는 선 색.
    태그 이름이 label_chars 를 넘으면 두 줄로 감쌉니다(라벨 폭은 가장 긴 줄에 맞춤)."""
    t = ui.chart_theme(scale)
    fs, fl = t["fs_axis"], t["fs_label"]
    rows = list(rows)[:max_rows]
    out = [f'<svg class="chart lift" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{H.escape(title, quote=True)}">']
    if not rows:
        out.append(f'<text x="{width / 2}" y="{height / 2}" class="tx" text-anchor="middle" style="font-size:{fl}px;fill:{t["ink3"]}">데이터 없음</text></svg>')
        return "".join(out)
    wrapped = [_wrap2(tag, label_chars) for tag, _, _ in rows]
    longest = max(len(ln) for lines in wrapped for ln in lines)
    label_w = int(longest * fl * .6)
    mult_w = fl * 5
    pad_l = label_w + fl
    row_h = height / len(rows)
    bar_h = min(fl * 1.6, row_h * .5)
    plot_w = width - pad_l - mult_w - t["dot"] * 3
    mx = max((c for _, c, _ in rows), default=1) or 1
    for k, ((tag, cnt, mult), lines) in enumerate(zip(rows, wrapped)):
        cy = (k + .5) * row_h
        is_hot = mult is not None and mult >= hot
        col = t["rise"] if is_hot else t["line_strong"]
        w = max(plot_w * cnt / mx, 2)
        y0 = cy - bar_h / 2
        out.append(f'<rect x="{pad_l:.1f}" y="{y0:.1f}" width="{w:.1f}" height="{bar_h:.1f}" style="fill:{col}"><title>{H.escape(tag)} · {cnt}개 · {_f(mult) if mult is not None else "—"}×</title></rect>')
        style = f"font-size:{fl}px;font-weight:{700 if is_hot else 500};fill:{t['ink'] if is_hot else t['ink2']}"
        if len(lines) == 1:
            out.append(f'<text class="tx" x="{pad_l - fl * .8:.1f}" y="{cy:.1f}" dy=".35em" text-anchor="end" style="{style}">{H.escape(lines[0])}</text>')
        else:
            out.append(f'<text class="tx" x="{pad_l - fl * .8:.1f}" y="{cy - fl * .6:.1f}" dy=".35em" text-anchor="end" style="{style}">{H.escape(lines[0])}</text>'
                       f'<text class="tx" x="{pad_l - fl * .8:.1f}" y="{cy + fl * .6:.1f}" dy=".35em" text-anchor="end" style="{style}">{H.escape(lines[1])}</text>')
        if w > fs * 3.5:
            out.append(f'<text x="{pad_l + w - fs * .7:.1f}" y="{cy:.1f}" dy=".35em" text-anchor="end" style="font-size:{fs + 1}px;font-weight:700;fill:{t["bg"] if is_hot else t["ink"]}">{cnt}</text>')
        else:
            out.append(f'<text x="{pad_l + w + fs * .6:.1f}" y="{cy:.1f}" dy=".35em" style="font-size:{fs + 1}px;font-weight:700;fill:{t["ink"]}">{cnt}</text>')
        mx_x = width - mult_w + t["dot"] * 1.5
        if mult is not None:
            out.append(f'<rect x="{mx_x - t["dot"]:.1f}" y="{cy - t["dot"]:.1f}" width="{t["dot"] * 2}" height="{t["dot"] * 2}" style="fill:{t["rise"] if is_hot else t["ink2"]}"/>')
            out.append(f'<text x="{mx_x + t["dot"] * 2.6:.1f}" y="{cy:.1f}" dy=".35em" style="font-size:{fl}px;font-weight:{700 if is_hot else 500};letter-spacing:-.02em;fill:{t["rise"] if is_hot else t["ink2"]}">{_f(mult)}×</text>')
        else:
            out.append(f'<text x="{mx_x + t["dot"] * 2.6:.1f}" y="{cy:.1f}" dy=".35em" style="font-size:{fl}px;fill:{t["ink3"]}">—</text>')
        if k:
            out.append(f'<line x1="{pad_l:.1f}" x2="{width}" y1="{k * row_h:.1f}" y2="{k * row_h:.1f}" style="stroke:{t["line_c"]};stroke-width:1"/>')
    out.append(f'<line x1="{pad_l:.1f}" x2="{pad_l:.1f}" y1="0" y2="{height}" style="stroke:{t["line_strong"]};stroke-width:1"/>')
    out.append("</svg>")
    return "".join(out)


# ---------- 산점도 ----------

def _ticks(lo, hi, log):
    import math
    if log:
        a, b = math.floor(math.log10(max(lo, 1))), math.ceil(math.log10(max(hi, 10)))
        return [10 ** k for k in range(a, b + 1)]
    span = hi - lo or 1
    step = 10 ** math.floor(math.log10(span / 4))
    for m in (1, 2, 5, 10):
        if span / (step * m) <= 6:
            step *= m
            break
    start = math.floor(lo / step) * step
    return [start + i * step for i in range(int((hi - start) / step) + 2)]


def _fmt_axis(v, kind):
    if kind == "pct":
        return f"{_f(v)}%"
    if kind == "usd":
        return f"${_f(v)}"
    if kind == "hours":
        return f"{_f(v)}h"
    if v >= 1000:
        return f"{v / 1000:g}K"
    return _f(v)


def scatter(points, width=936, height=620, scale="web", x_log=False, y_log=False, x_kind="num", y_kind="num",
            x_label="", y_label="", quadrant=None, none_label="", title="", size_range=(4, 16), label_chars=16):
    """points: [(이름, x, y, size, kind)] — kind: "" 보통 · "label" 라벨만 · "hi" 초록 강조+라벨 · "pick" 흰 테두리 강조+라벨.
    y 가 None 인 점은 아래 점선 줄(none_label) 위에 둡니다. quadrant = {"x": x경계, "y": y경계, "label": "틈새"} 면 왼쪽 위 사분면에 옅은 초록 음영.
    x_kind/y_kind: num | pct | usd | hours (축 라벨 형식)."""
    import math
    t = ui.chart_theme(scale)
    fs, fl = t["fs_axis"], t["fs_label"]
    pts = [p for p in points if p[1] is not None]
    out = [f'<svg class="chart scat" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{H.escape(title, quote=True)}">']
    if not pts:
        out.append(f'<text x="{width / 2}" y="{height / 2}" class="tx" text-anchor="middle" style="font-size:{fl}px;fill:{t["ink3"]}">데이터 없음</text></svg>')
        return "".join(out)
    has_none = any(p[2] is None for p in pts)
    pad_l, pad_r, pad_t = fs * 4.6, fs * 2, fs * 2.2
    pad_b = fs * 3.2 + (fs * 2.4 if has_none else 0)
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
    xs = [p[1] for p in pts]
    ys = [p[2] for p in pts if p[2] is not None]
    x_lo, x_hi = min(xs), max(xs)
    if x_log:
        x_lo, x_hi = max(x_lo, 1), max(x_hi, 10)
        lx0, lx1 = math.log10(x_lo) - .08, math.log10(x_hi) + .08
    else:
        span = (x_hi - x_lo) or 1
        lx0, lx1 = max(0, x_lo - span * .06) if x_lo >= 0 else x_lo - span * .06, x_hi + span * .06
    y_lo, y_hi = (min(ys), max(ys)) if ys else (0, 1)
    if y_log:
        y_lo, y_hi = max(y_lo, .01), max(y_hi, .1)
        ly0, ly1 = math.log10(y_lo) - .1, math.log10(y_hi) + .1
    else:
        span = (y_hi - y_lo) or 1
        ly0, ly1 = (max(0, y_lo - span * .08) if y_lo >= 0 else y_lo - span * .08), y_hi + span * .12

    def X(v):
        v = math.log10(max(v, 1e-9)) if x_log else v
        return pad_l + (v - lx0) / (lx1 - lx0) * plot_w

    def Y(v):
        v = math.log10(max(v, 1e-9)) if y_log else v
        return pad_t + (1 - (v - ly0) / (ly1 - ly0)) * plot_h

    # 사분면 음영
    if quadrant:
        qx, qy = X(quadrant["x"]), Y(quadrant["y"])
        out.append(f'<rect x="{pad_l}" y="{pad_t}" width="{max(qx - pad_l, 0):.1f}" height="{max(qy - pad_t, 0):.1f}" style="fill:{t["rise"]};opacity:.08"/>')
        out.append(f'<line x1="{qx:.1f}" x2="{qx:.1f}" y1="{pad_t}" y2="{pad_t + plot_h:.1f}" style="stroke:{t["rise"]};stroke-width:1;stroke-dasharray:4 4;opacity:.6"/>')
        out.append(f'<line x1="{pad_l}" x2="{pad_l + plot_w:.1f}" y1="{qy:.1f}" y2="{qy:.1f}" style="stroke:{t["rise"]};stroke-width:1;stroke-dasharray:4 4;opacity:.6"/>')
        if quadrant.get("label"):
            out.append(f'<text class="tx" x="{pad_l + fs:.1f}" y="{pad_t + fs * 1.6:.1f}" style="font-size:{fl}px;font-weight:700;letter-spacing:.06em;fill:{t["rise"]}">{H.escape(quadrant["label"])}</text>')
    # 축·안내선
    for v in _ticks(x_lo, x_hi, x_log):
        x = X(v)
        if pad_l - 1 <= x <= pad_l + plot_w + 1:
            out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{pad_t}" y2="{pad_t + plot_h:.1f}" style="stroke:{t["line_c"]};stroke-width:1"/>')
            out.append(f'<text x="{x:.1f}" y="{pad_t + plot_h + fs * 1.5:.1f}" text-anchor="middle" style="font-size:{fs}px;fill:{t["ink2"]}">{_fmt_axis(v, x_kind)}</text>')
    for v in _ticks(y_lo, y_hi, y_log):
        y = Y(v)
        if pad_t - 1 <= y <= pad_t + plot_h + 1:
            out.append(f'<line x1="{pad_l}" x2="{pad_l + plot_w:.1f}" y1="{y:.1f}" y2="{y:.1f}" style="stroke:{t["line_c"]};stroke-width:1"/>')
            out.append(f'<text x="{pad_l - fs * .7:.1f}" y="{y:.1f}" dy=".35em" text-anchor="end" style="font-size:{fs}px;fill:{t["ink2"]}">{_fmt_axis(v, y_kind)}</text>')
    out.append(f'<rect x="{pad_l}" y="{pad_t}" width="{plot_w:.1f}" height="{plot_h:.1f}" style="fill:none;stroke:{t["line_strong"]};stroke-width:1"/>')
    if x_label:
        out.append(f'<text x="{pad_l + plot_w:.1f}" y="{pad_t + plot_h + fs * 2.9:.1f}" text-anchor="end" style="font-size:{fs}px;letter-spacing:.06em;fill:{t["ink3"]}">{H.escape(x_label)}</text>')
    if y_label:
        out.append(f'<text x="{pad_l:.1f}" y="{pad_t - fs * .9:.1f}" style="font-size:{fs}px;letter-spacing:.06em;fill:{t["ink3"]}">{H.escape(y_label)}</text>')
    none_y = pad_t + plot_h + fs * 4.4
    if has_none:
        out.append(f'<line x1="{pad_l}" x2="{pad_l + plot_w:.1f}" y1="{none_y:.1f}" y2="{none_y:.1f}" style="stroke:{t["line_strong"]};stroke-width:1;stroke-dasharray:5 4"/>')
        out.append(f'<text x="{pad_l - fs * .7:.1f}" y="{none_y:.1f}" dy=".35em" text-anchor="end" style="font-size:{fs}px;fill:{t["ink3"]}">{H.escape(none_label or "미상")}</text>')
    # 점: 보통 → 라벨 → 강조 순
    sizes = [p[3] or 0 for p in pts]
    s_lo, s_hi = min(sizes), max(sizes)

    def R(sz):
        if s_hi == s_lo:
            return (size_range[0] + size_range[1]) / 2
        return size_range[0] + (math.sqrt(max(sz or 0, 0)) - math.sqrt(max(s_lo, 0))) / (math.sqrt(max(s_hi, 0)) - math.sqrt(max(s_lo, 0)) or 1) * (size_range[1] - size_range[0])
    order = sorted(pts, key=lambda p: (0 if p[4] == "" else 1 if p[4] == "label" else 2))
    placed = []
    for name, x, y, sz, kind in order:
        cx, cy = X(x), (none_y if y is None else Y(y))
        r = R(sz)
        if kind == "hi":
            style = f"fill:{t['rise']};fill-opacity:.85;stroke:{t['bg']};stroke-width:1.5"
        elif kind == "pick":
            style = f"fill:{t['rise']};stroke:{t['ink']};stroke-width:2"
        elif kind == "label":
            style = f"fill:{t['ink2']};fill-opacity:.8;stroke:{t['bg']};stroke-width:1"
        else:
            style = f"fill:{t['line_strong']};fill-opacity:.75;stroke:{t['bg']};stroke-width:1"
        tip = f"{name} · {_fmt_axis(x, x_kind)} · {_fmt_axis(y, y_kind) if y is not None else none_label or '미상'}" + (f" · {_f(sz)}" if sz else "")
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" style="{style}"><title>{H.escape(tip)}</title></circle>')
        if kind in ("label", "hi", "pick"):
            text = _trunc(name, label_chars)
            tw, th = len(text) * fl * .58, fl * 1.2
            cands = [(cx + r + 4, cy, "start"), (cx - r - 4, cy, "end"), (cx, cy - r - th * .6, "middle"), (cx, cy + r + th * .9, "middle")]
            for lx, ly, anchor in cands:
                x0 = lx if anchor == "start" else lx - tw if anchor == "end" else lx - tw / 2
                box = (x0, ly - th / 2, x0 + tw, ly + th / 2)
                if box[0] < pad_l - 2 or box[2] > width - 2:
                    continue
                if not any(not (box[2] < b[0] or box[0] > b[2] or box[3] < b[1] or box[1] > b[3]) for b in placed):
                    placed.append(box)
                    col = t["rise"] if kind == "hi" else t["ink"] if kind == "pick" else t["ink2"]
                    out.append(f'<text class="tx" x="{lx:.1f}" y="{ly:.1f}" dy=".35em" text-anchor="{anchor}" style="font-size:{fl}px;font-weight:{700 if kind != "label" else 500};fill:{col};paint-order:stroke;stroke:{t["bg"]};stroke-width:3px;stroke-linejoin:round">{H.escape(text)}</text>')
                    break
    out.append("</svg>")
    return "".join(out)


# ---------- 도넛 ----------

def donut(parts, width=320, height=200, scale="web", title="", center_label="", colors=None):
    """parts: [(라벨, 값)]. 왼쪽 고리(선 두께 = 지름의 18%), 가운데 합계, 오른쪽 범례(네모 + 라벨 + 값·비율).
    색은 colors(CSS 변수 목록) 또는 기본 [강조, 글자_1, 선_진함, 경고]."""
    import math
    t = ui.chart_theme(scale)
    fs, fl = t["fs_axis"], t["fs_label"]
    cols = colors or [t["accent"], t["ink"], t["line_strong"], t["warn"]]
    parts = [(l, v) for l, v in parts if v]
    total = sum(v for _, v in parts)
    out = [f'<svg class="chart donut" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{H.escape(title, quote=True)}">']
    if not total:
        out.append(f'<text x="{width / 2}" y="{height / 2}" class="tx" text-anchor="middle" style="font-size:{fl}px;fill:{t["ink3"]}">데이터 없음</text></svg>')
        return "".join(out)
    d = min(height, width * .45)
    cx, cy, r = d / 2 + 2, height / 2, d / 2 - 4
    sw = r * .36
    rr = r - sw / 2
    circ = 2 * math.pi * rr
    acc = 0
    for i, (l, v) in enumerate(parts):
        frac = v / total
        dash = max(circ * frac - 2, 0)
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rr:.1f}" style="fill:none;stroke:{cols[i % len(cols)]};stroke-width:{sw:.1f};stroke-dasharray:{dash:.2f} {circ - dash:.2f};stroke-dashoffset:{-acc * circ + circ / 4:.2f}"><title>{H.escape(l)} {v} ({frac * 100:.0f}%)</title></circle>')
        acc += frac
    out.append(f'<text x="{cx:.1f}" y="{cy - fs * .2:.1f}" text-anchor="middle" style="font-size:{fl * 1.8}px;font-weight:700;letter-spacing:-.03em;fill:{t["ink"]}">{total}</text>')
    out.append(f'<text x="{cx:.1f}" y="{cy + fs * 1.3:.1f}" text-anchor="middle" style="font-size:{fs}px;letter-spacing:.06em;fill:{t["ink2"]}">{H.escape(center_label or "건")}</text>')
    lx = cx + r + fs * 1.6
    row_h = fl * 2
    ly0 = cy - (len(parts) - 1) * row_h / 2
    for i, (l, v) in enumerate(parts):
        y = ly0 + i * row_h
        out.append(f'<rect x="{lx:.1f}" y="{y - fl * .45:.1f}" width="{fl * .9:.1f}" height="{fl * .9:.1f}" style="fill:{cols[i % len(cols)]}"/>')
        out.append(f'<text class="tx" x="{lx + fl * 1.5:.1f}" y="{y:.1f}" dy=".35em" style="font-size:{fl}px;font-weight:600;fill:{t["ink"]}">{H.escape(l)}</text>')
        out.append(f'<text x="{width - 2:.1f}" y="{y:.1f}" dy=".35em" text-anchor="end" style="font-size:{fl}px;fill:{t["ink2"]}">{v} · {v / total * 100:.0f}%</text>')
    out.append("</svg>")
    return "".join(out)
