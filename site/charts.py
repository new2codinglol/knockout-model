"""Inline-SVG chart builders for the WC2026 model site (Neon Onyx theme).

Every chart is a self-contained <svg> string rendered at build time, readable
with no JavaScript. Text (labels, values, axes) is emitted in theme text
colours via CSS classes defined in template.html, never in a series colour.
Series colours are the spec's validated categorical slots, fixed order:

    slot 1  #16a34a  green
    slot 2  #c026d3  magenta
    slot 3  #3b82f6  blue

Direct labels are drawn on multi-series charts as the mandated secondary
encoding (the green<->magenta pair sits in the CVD floor band).
"""
from html import escape

SLOT1 = "#16a34a"   # green
SLOT2 = "#c026d3"   # magenta
SLOT3 = "#3b82f6"   # blue
GOOD = "#4ade80"    # status good (neon green)
BAD = "#f43f5e"     # status bad
MID = "#6b7280"     # neutral gray midline
DRAW_LINE = "#8a9190"  # lighter neutral for 2px draw line (fill gray too dark on onyx)

# subtle neon glow per colour (drop-shadow ~35-45% alpha)
_GLOW = {
    SLOT1: "rgba(22,163,74,.40)",
    SLOT2: "rgba(192,38,211,.40)",
    SLOT3: "rgba(59,130,246,.42)",
    GOOD:  "rgba(74,222,128,.45)",
}


def _glow(hex_):
    return f"filter:drop-shadow(0 0 5px {_GLOW.get(hex_, 'transparent')})"


def _pct(x, dp=1):
    return f"{x * 100:.{dp}f}%"


def _svg(w, h, aria, body):
    return (
        f'<svg class="chart" viewBox="0 0 {w} {h}" role="img" '
        f'aria-label="{escape(aria)}" preserveAspectRatio="xMidYMid meet" '
        f'style="width:100%;height:auto">{body}</svg>'
    )


# ------------------------------------------------------------ 1. winner probs
def winner_chart(winner_blend, winner_model):
    """Horizontal bars: winner_blend (green), diamond marker at winner_model.

    If winner_blend is falsy, plot winner_model alone (drop marker + legend).
    """
    blended = bool(winner_blend)
    use = winner_blend if blended else winner_model
    rows = sorted(use.items(), key=lambda kv: -kv[1])
    n = len(rows)

    W = 640
    row_h = 50
    top = 40 if blended else 16
    bot = 10
    H = top + n * row_h + bot
    lab_w = 108
    x0, x1 = lab_w, W - 66
    dmax = max(list(use.values()) + list(winner_model.values())) or 1.0

    def sx(v):
        return x0 + (v / dmax) * (x1 - x0)

    parts = []

    if blended:
        # inline legend: blend bar swatch + model-only diamond
        parts.append(
            f'<rect x="{lab_w}" y="14" width="22" height="11" rx="3" fill="{SLOT1}"/>'
            f'<text class="c-lab" x="{lab_w + 28}" y="23">blend</text>'
            f'<path d="M{lab_w + 96} 13 l7 7 -7 7 -7 -7 z" fill="none" '
            f'stroke="var(--ink)" stroke-width="2"/>'
            f'<text class="c-lab" x="{lab_w + 108}" y="23">model only</text>'
        )

    for i, (team, pb) in enumerate(rows):
        pm = winner_model.get(team, pb)
        cy = top + i * row_h + row_h / 2
        bx = sx(pb)
        title = (f"{team}: blend {_pct(pb)}, model {_pct(pm)}" if blended
                 else f"{team}: {_pct(pb)}")
        parts.append(f'<title>{escape(title)}</title>')
        parts.append(
            f'<text class="c-lab team" x="{x0 - 12}" y="{cy + 5}" '
            f'text-anchor="end">{escape(team)}</text>'
        )
        parts.append(
            f'<g><title>{escape(title)}</title>'
            f'<rect x="{x0}" y="{cy - 9:.1f}" width="{max(bx - x0, 0):.1f}" height="18" '
            f'rx="3" fill="{SLOT1}" style="{_glow(SLOT1)}"/></g>'
        )
        vx = bx
        if blended:
            mx = sx(pm)
            vx = max(bx, mx)   # keep the value clear of the model diamond
            parts.append(
                f'<path d="M{mx:.1f} {cy - 8:.1f} l8 8 -8 8 -8 -8 z" '
                f'fill="var(--bg)" stroke="var(--ink)" stroke-width="2"/>'
            )
        parts.append(
            f'<text class="c-val" x="{vx + 12:.1f}" y="{cy + 5}">{_pct(pb)}</text>'
        )

    aria = "Chance of winning the tournament, " + ", ".join(
        f"{t} {_pct(p)}" for t, p in rows)
    return _svg(W, H, aria, "".join(parts))


# ----------------------------------------------------- 2. model - market div.
def divergence_chart(team_a, team_b, model, market):
    """Diverging horizontal bars: (model - market) in pts per outcome.

    Green pole = model higher than market; magenta pole = market higher.
    """
    outcomes = [
        (f"{team_a} win", model["win"] - market["win"]),
        ("Draw", model["draw"] - market["draw"]),
        (f"{team_b} win", model["loss"] - market["loss"]),
    ]
    diffs = [d * 100 for _, d in outcomes]  # pts
    amax = max(4.0, max(abs(d) for d in diffs))
    # round axis up to a tidy step
    step = 5 if amax <= 20 else 10
    amax = step * (int(amax / step) + 1)

    W = 640
    lab_w = 128
    row_h = 54
    top = 16
    ax_h = 46
    n = len(outcomes)
    H = top + n * row_h + ax_h
    px0, px1 = lab_w, W - 58   # right margin holds the value label at max bar
    cx = (px0 + px1) / 2

    def dx(pts):
        return cx + (pts / amax) * (px1 - cx)

    parts = []
    plot_bot = top + n * row_h

    # gridlines + axis ticks
    for t in range(-amax, amax + 1, step):
        gx = dx(t)
        is_zero = t == 0
        parts.append(
            f'<line class="c-grid{" zero" if is_zero else ""}" x1="{gx:.1f}" '
            f'y1="{top}" x2="{gx:.1f}" y2="{plot_bot}"/>'
        )
        parts.append(
            f'<text class="c-axis" x="{gx:.1f}" y="{plot_bot + 17}" '
            f'text-anchor="middle">{t:+d}</text>'
        )
    parts.append(
        f'<text class="c-axis" x="{cx:.1f}" y="{plot_bot + 38}" text-anchor="middle">'
        f'model &minus; market (pts)</text>'
    )

    for i, (label, d) in enumerate(outcomes):
        pts = d * 100
        cy = top + i * row_h + row_h / 2
        col = SLOT1 if pts >= 0 else SLOT2
        end = dx(pts)
        x = min(cx, end)
        w = abs(end - cx)
        who = "model higher" if pts >= 0 else "market higher"
        parts.append(
            f'<text class="c-lab" x="{px0 - 12}" y="{cy + 5:.1f}" '
            f'text-anchor="end">{escape(label)}</text>'
        )
        parts.append(
            f'<g><title>{escape(f"{label}: {pts:+.1f} pts ({who})")}</title>'
            f'<rect x="{x:.1f}" y="{cy - 9:.1f}" width="{max(w, 0.6):.1f}" height="18" '
            f'rx="3" fill="{col}" style="{_glow(col)}"/></g>'
        )
        vx = end + (8 if pts >= 0 else -8)
        anchor = "start" if pts >= 0 else "end"
        parts.append(
            f'<text class="c-val" x="{vx:.1f}" y="{cy + 5:.1f}" '
            f'text-anchor="{anchor}">{pts:+.1f}</text>'
        )

    aria = "Model minus market divergence in points: " + ", ".join(
        f"{lbl} {d * 100:+.1f}" for lbl, d in outcomes)
    return _svg(W, H, aria, "".join(parts))


# ---------------------------------------------------------- 3. odds timeline
def timeline_chart(snapshots, team_a, team_b):
    """Line chart of consensus implied probability over snapshots.

    snapshots: list of dicts {t: datetime, label: str, home, draw, away, books}
    ordered by time. Series wear the entity colours (green/grey/magenta),
    direct-labeled at line ends.
    Returns (svg, details_table_html).
    """
    # colours follow the entities of the stacked W/D/L bars above:
    # team A green, draw neutral grey, team B magenta
    series = [
        (f"{team_a} win", "home", SLOT1),
        ("Draw", "draw", DRAW_LINE),
        (f"{team_b} win", "away", SLOT2),
    ]
    vals = [s[k] for s in snapshots for _, k, _ in series]
    ymin = min(vals)
    ymax = max(vals)
    pad = max(0.02, (ymax - ymin) * 0.25)
    lo = max(0.0, ymin - pad)
    hi = min(1.0, ymax + pad)
    if hi - lo < 0.06:
        lo, hi = max(0, lo - 0.03), min(1, hi + 0.03)

    W = 680
    top, bot = 20, 44
    left, right = 46, 150   # right margin holds direct labels
    H = 300
    px0, px1 = left, W - right
    py0, py1 = top, H - bot
    n = len(snapshots)

    def X(i):
        return px0 if n == 1 else px0 + i / (n - 1) * (px1 - px0)

    def Y(v):
        return py1 - (v - lo) / (hi - lo) * (py1 - py0)

    parts = []

    # y gridlines / axis at honest whole-percent steps
    import math
    span_pct = (hi - lo) * 100
    tick_step = next(s for s in (1, 2, 5, 10, 20) if span_pct / s <= 6)
    t = math.ceil(lo * 100 / tick_step) * tick_step
    while t <= hi * 100 + 1e-9:
        gy = Y(t / 100)
        parts.append(
            f'<line class="c-grid" x1="{px0}" y1="{gy:.1f}" x2="{px1}" y2="{gy:.1f}"/>'
        )
        parts.append(
            f'<text class="c-axis" x="{px0 - 8}" y="{gy + 4:.1f}" '
            f'text-anchor="end">{t:.0f}%</text>'
        )
        t += tick_step

    # x ticks (snapshot times)
    for i, s in enumerate(snapshots):
        gx = X(i)
        parts.append(
            f'<text class="c-axis" x="{gx:.1f}" y="{py1 + 18:.1f}" '
            f'text-anchor="middle">{escape(s["label"])}</text>'
        )

    # lines + points + end labels
    # nudge overlapping end-labels apart
    ends = sorted(series, key=lambda sr: Y(snapshots[-1][sr[1]]))
    last_y = None
    label_y = {}
    for _, key, _c in ends:
        y = Y(snapshots[-1][key])
        if last_y is not None and y - last_y < 14:
            y = last_y + 14
        label_y[key] = y
        last_y = y

    for name, key, col in series:
        pts = " ".join(f"{X(i):.1f},{Y(s[key]):.1f}" for i, s in enumerate(snapshots))
        parts.append(
            f'<polyline points="{pts}" fill="none" stroke="{col}" '
            f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round" '
            f'style="{_glow(col)}"/>'
        )
        for i, s in enumerate(snapshots):
            cxp, cyp = X(i), Y(s[key])
            tip = f'{s["label"]} — {name}: {_pct(s[key])} ({s["books"]} books)'
            parts.append(
                f'<g><title>{escape(tip)}</title>'
                f'<circle cx="{cxp:.1f}" cy="{cyp:.1f}" r="4" fill="{col}" '
                f'stroke="var(--bg)" stroke-width="1.5"/></g>'
            )
        ly = label_y[key]
        parts.append(
            f'<text class="c-end" x="{px1 + 10:.1f}" y="{ly + 4:.1f}" fill="{col}">'
            f'{escape(name)} {_pct(snapshots[-1][key])}</text>'
        )

    aria = ("Consensus implied probability over " + str(n) + " odds snapshots: "
            + ", ".join(f"{nm} ends {_pct(snapshots[-1][k])}" for nm, k, _ in series))
    svg = _svg(W, H, aria, "".join(parts))

    # accessibility fallback table
    head = "".join(f"<th>{escape(nm)}</th>" for nm, _, _ in series)
    trows = []
    for s in snapshots:
        cells = "".join(f'<td class="num">{_pct(s[k])}</td>' for _, k, _ in series)
        trows.append(
            f'<tr><td>{escape(s["full"])}</td>{cells}'
            f'<td class="num">{s["books"]}</td></tr>'
        )
    table = (
        '<details class="c-details"><summary>Consensus values table</summary>'
        '<div class="tablewrap"><table><thead><tr><th>Snapshot</th>'
        f'{head}<th>Books</th></tr></thead><tbody>{"".join(trows)}'
        '</tbody></table></div></details>'
    )
    return svg, table


# --------------------------------------------------------- 4. calibration dots
def calibration_chart(retro):
    """Dot strip: x = match date, y = model prob for the outcome that happened.

    hit (called yes) = filled green dot; miss = red ring. Reference at 33.3%.
    """
    import datetime as _dt

    pts = []
    for r in retro:
        p = _p_actual(r)
        d = _dt.date.fromisoformat(r["date"])
        pts.append((d, p, r["called"] == "yes", r))

    dmin = min(p[0] for p in pts)
    dmax = max(p[0] for p in pts)
    span = max((dmax - dmin).days, 1)

    W = 680
    top, bot = 18, 40
    left, right = 46, 18
    H = 300
    px0, px1 = left, W - right
    py0, py1 = top, H - bot

    def X(d):
        return px0 + (d - dmin).days / span * (px1 - px0)

    def Y(v):
        return py1 - v * (py1 - py0)   # 0..1

    parts = []
    for j in range(0, 101, 25):
        gy = Y(j / 100)
        parts.append(
            f'<line class="c-grid" x1="{px0}" y1="{gy:.1f}" x2="{px1}" y2="{gy:.1f}"/>'
        )
        parts.append(
            f'<text class="c-axis" x="{px0 - 8}" y="{gy + 4:.1f}" '
            f'text-anchor="end">{j}%</text>'
        )

    # reference line at 33.3% (coin-flip across 3 outcomes)
    ry = Y(1 / 3)
    parts.append(
        f'<line class="c-ref" x1="{px0}" y1="{ry:.1f}" x2="{px1}" y2="{ry:.1f}"/>'
    )
    parts.append(
        f'<text class="c-axis ref" x="{px1}" y="{ry - 6:.1f}" text-anchor="end">'
        f'33% baseline</text>'
    )

    # month ticks along x
    seen = set()
    for d, _p, _h, _r in pts:
        key = (d.year, d.month)
        if key in seen:
            continue
        seen.add(key)
        first = _dt.date(d.year, d.month, 1)
        gx = X(max(first, dmin))
        parts.append(
            f'<text class="c-axis" x="{gx:.1f}" y="{py1 + 20:.1f}" '
            f'text-anchor="middle">{d.strftime("%b")}</text>'
        )

    # jitter dots sharing an x
    from collections import defaultdict
    by_x = defaultdict(list)
    for pt in pts:
        by_x[pt[0]].append(pt)
    for d, group in by_x.items():
        c = len(group)
        for k, (dd, p, hit, r) in enumerate(sorted(group, key=lambda g: -g[1])):
            off = (k - (c - 1) / 2) * 9
            cxp = X(d) + off
            cyp = Y(p)
            title = (f'{dd.strftime("%d %b")} — {r["match"]}: model {_pct(p)} for '
                     f'the actual result ({r["actual"]}), '
                     f'{"called" if hit else "missed"}')
            if hit:
                mark = (f'<circle cx="{cxp:.1f}" cy="{cyp:.1f}" r="5" fill="{GOOD}" '
                        f'style="{_glow(GOOD)}"/>')
            else:
                mark = (f'<circle cx="{cxp:.1f}" cy="{cyp:.1f}" r="5" fill="none" '
                        f'stroke="{BAD}" stroke-width="2.5"/>')
            parts.append(f'<g><title>{escape(title)}</title>{mark}</g>')

    hits = sum(1 for p in pts if p[2])
    aria = (f"Calibration: model probability for the outcome that happened in "
            f"{len(pts)} matches; {hits} called correctly. Filled green dots are "
            f"hits, red rings are misses. Reference line at 33 percent.")
    return _svg(W, H, aria, "".join(parts))


def _p_actual(r):
    """Model probability assigned to the outcome that actually happened."""
    score = r["actual"].split()[0]        # "1-1 (pens)" -> "1-1"
    a, b = (int(x) for x in score.split("-"))
    if a > b:
        return r["p_win"]
    if a < b:
        return r["p_loss"]
    return r["p_draw"]
