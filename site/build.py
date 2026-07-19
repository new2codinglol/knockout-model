"""Generate site/index.html from data/site_data.json (+ data/odds_history.csv)
and site/template.html.

Run after each `python predict.py` run:

    python site/build.py

Every number and chart on the page is rendered as static markup here (inline
SVG built in site/charts.py); the page needs no JavaScript to be read. The raw
JSON payload is inlined into a <script type="application/json"> block.

The page renders from data, not hardcoded team names: the bracket changes as
the tournament progresses. Sections that depend on market/odds data (the
featured-match divergence and the odds timeline) drop out cleanly when that
data is absent — see the Resilience section of SPEC.md.
"""
import csv
import json
import re
import statistics
from datetime import datetime, date
from html import escape
from pathlib import Path

import charts

HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "data" / "site_data.json"
ODDS = HERE.parent / "data" / "odds_history.csv"

d = json.loads(DATA.read_text(encoding="utf-8"))


def pct(x, dp=1):
    return f"{x * 100:.{dp}f}%"


def fmt_date(iso):
    return date.fromisoformat(iso).strftime("%d %b").lstrip("0")


def _steam(s, team_a):
    """Human line-movement note, parsed generically from the steam string."""
    m = re.match(r"home ([\d.]+)%->([\d.]+)% \(([+-][\d.]+)%, (\d+) snapshots\)", s or "")
    if not m:
        return s or "no line-movement data."
    if m.group(1) == m.group(2):
        return (f"the market hasn&rsquo;t moved &mdash; {team_a} held at {m.group(2)}% "
                f"across all {m.group(4)} odds snapshots.")
    return (f"the consensus on {team_a} moved {m.group(1)}% &rarr; {m.group(2)}% "
            f"({m.group(3)}%) across {m.group(4)} snapshots.")


# --- featured-match W/D/L stacked bar (A win | draw | B win), CSS, no SVG ---
def wdl_bar(team_a, team_b, probs, slim_below=0.10):
    segs = []
    parts = (("a", probs["win"], f"{team_a} win"),
             ("d", probs["draw"], "draw"),
             ("b", probs["loss"], f"{team_b} win"))
    for cls, p, name in parts:
        slim = " slim" if p < slim_below else ""
        segs.append(
            f'<span class="seg {cls}{slim}" style="flex-grow:{round(p * 1000)}" '
            f'title="{name}: {pct(p)}">{pct(p)}</span>'
        )
    aria = (f"{team_a} win {pct(probs['win'])}, draw {pct(probs['draw'])}, "
            f"{team_b} win {pct(probs['loss'])}")
    return f'<div class="wdl" role="img" aria-label="{aria}">{"".join(segs)}</div>'


# ============================================================ 1. winner chart
winner_svg = charts.winner_chart(d.get("winner_blend"), d["winner_model"])
blended = bool(d.get("winner_blend"))
win_src = d["winner_blend"] if blended else d["winner_model"]
win_tbl_rows = "".join(
    f'<tr><td>{team}</td><td class="num">{pct(pb)}</td>'
    f'<td class="num">{pct(d["winner_model"][team])}</td></tr>'
    for team, pb in sorted(win_src.items(), key=lambda kv: -kv[1])
)
winner_note = (
    f'Bar: published blend ({100 - round(d["blend_weight_model"] * 100)}% market / '
    f'{round(d["blend_weight_model"] * 100)}% model). Diamond marks the model-only estimate.'
    if blended else "Model-only estimate (no market blend available)."
)

# ======================================================= featured + timeline
# feature the Final when the books price it, else the first priced match
featured = next((m for m in d["matches"] if m.get("market") and m["label"] == "Final"),
                next((m for m in d["matches"] if m.get("market")), None))
odds_snaps = []


def load_odds(team_a, team_b):
    """Consensus implied prob per snapshot for the featured pairing.

    'home' in each snap means team_a (rows are flipped if the books list the
    pairing the other way round), so series line up with the featured panel.
    """
    if not ODDS.exists():
        return []
    rows = list(csv.DictReader(ODDS.read_text(encoding="utf-8").splitlines()))
    from collections import defaultdict
    groups = defaultdict(list)
    for r in rows:
        if {r["home_team"], r["away_team"]} == {team_a, team_b}:
            groups[r["fetched_at"]].append(r)

    snaps = []
    for fetched, books in sorted(groups.items()):
        h, dr, a = [], [], []
        for b in books:
            try:
                oh, od, oa = float(b["home_odds"]), float(b["draw_odds"]), float(b["away_odds"])
            except (ValueError, KeyError):
                continue
            if b["home_team"] != team_a:
                oh, oa = oa, oh
            imp = [1 / oh, 1 / od, 1 / oa]
            s = sum(imp)
            h.append(imp[0] / s)
            dr.append(imp[1] / s)
            a.append(imp[2] / s)
        if not h:
            continue
        t = datetime.fromisoformat(fetched.replace("Z", "+00:00"))
        snaps.append({
            "t": t,
            "label": t.strftime("%H:%M"),
            "full": t.strftime("%d %b %H:%M UTC"),
            "home": statistics.median(h),
            "draw": statistics.median(dr),
            "away": statistics.median(a),
            "books": len(h),
        })
    # if every snapshot is the same calendar day, times alone read fine
    return snaps


odds_snaps = load_odds(*featured["teams"]) if featured else []


def panel(title, body, span=6, note=""):
    note_html = f'<p class="chart-note">{note}</p>' if note else ""
    return (f'<section class="panel c{span}">'
            f'<h3 class="panel-h">{title}</h3>{body}{note_html}</section>')


featured_wdl_panel = ""
divergence_panel = ""
timeline_panel = ""
div_big_pts = None   # for the KPI row
div_lbl = None

if featured:
    ta, tb = featured["teams"]
    div_svg = charts.divergence_chart(ta, tb, featured["model"], featured["market"])

    # W/D/L rows: model / market / blend (blend optional)
    rows = [("Model", featured["model"], featured.get("model_advance"))]
    rows.append(("Market consensus", featured["market"], None))
    if featured.get("blend"):
        rows.append(("Published blend", featured["blend"], featured.get("blend_advance")))
    row_html = []
    for name, probs, adv in rows:
        adv_html = (f'<span class="r-adv">{tb} advances <b>{pct(1 - adv)}</b></span>'
                    if adv is not None else "")
        row_html.append(
            f'<div class="rrow"><div class="rlabel"><span>{name}</span>{adv_html}</div>'
            f'{wdl_bar(ta, tb, probs)}</div>'
        )

    # headline divergence = outcome with the largest |model - market|
    outs = [(f"{ta} win", featured["model"]["win"] - featured["market"]["win"]),
            ("draw", featured["model"]["draw"] - featured["market"]["draw"]),
            (f"{tb} win", featured["model"]["loss"] - featured["market"]["loss"])]
    div_lbl, big = max(outs, key=lambda o: abs(o[1]))
    div_big_pts = big * 100

    steam = _steam(featured.get("steam", ""), ta)

    featured_wdl_panel = panel(
        f'{ta} v {tb} &middot; 90-min W/D/L',
        f'<div class="legend" aria-hidden="true">'
        f'<span class="sw-a"><i></i>{ta} win</span>'
        f'<span class="sw-d"><i></i>Draw</span>'
        f'<span class="sw-b"><i></i>{tb} win</span></div>'
        f'{"".join(row_html)}',
        span=6,
        note='&ldquo;Advances&rdquo; folds in extra time and penalties. '
             'Market: de-vigged bookmaker consensus, 90 minutes only.',
    )
    divergence_panel = panel(
        "Model &minus; market divergence",
        f'{div_svg}<div class="steam"><b>Line check:</b> {steam}</div>',
        span=6,
        note='Green = model rates it higher than the books; magenta = the books rate it higher.',
    )

    if odds_snaps:
        tl_svg, tl_table = charts.timeline_chart(odds_snaps, ta, tb)
        span_days = {s["t"].date() for s in odds_snaps}
        day_note = (f'All snapshots on {sorted(span_days)[0].strftime("%d %b %Y")}.'
                    if len(span_days) == 1 else "Times are UTC.")
        timeline_panel = panel(
            "Odds movement &middot; implied probability",
            f'{tl_svg}{tl_table}',
            span=8,
            note=f'Consensus across ~{odds_snaps[0]["books"]} books per snapshot '
                 f'(each de-vigged, median taken). {day_note}',
        )


# ================================================================= fixtures
others = [m for m in d["matches"] if m is not featured]
fixture_rows = []
for mx in others:
    a, b = mx["teams"]
    label = mx["label"]
    kind = label.split("(")[0].strip() or "Fixture"
    cond = label.split("(")[-1].rstrip(")") if "(" in label else ""
    cond_html = f'<span class="fx-cond">{cond} &middot; {pct(mx["p_pairing"], 0)} likely</span>' if cond else ""
    p_a = mx["model_advance"]
    fav, p_fav = (a, p_a) if p_a >= 0.5 else (b, 1 - p_a)
    fixture_rows.append(f'''<div class="fixture">
  <div class="fx-head"><span class="fx-date">{fmt_date(mx["date"])} &middot; {kind}</span>{cond_html}</div>
  <div class="fx-teams"><span>{a}</span><span>{b}</span></div>
  {wdl_bar(a, b, mx["model"])}
  <p class="fx-note"><b>{fav} {pct(p_fav)}</b> to advance</p>
</div>''')

fixtures_note = ("Model probabilities only" +
                 ("" if any(m.get("market") for m in others) else
                  " &mdash; the books had not priced these pairings at the last data pull") +
                 ". The advance call folds in extra time and penalties.")

# ============================================== V2 extras: goals + player props
# Per match with an `extras` block. Every field may be null per-row (books don't
# quote every line/player); a null model value drops the row, a null market value
# drops that bar/tick but keeps the row. A match without `extras` renders nothing.
GM_LEGEND = ('<div class="gm-legend" aria-hidden="true">'
             '<span class="l-mdl"><i></i>model</span>'
             '<span class="l-mkt"><i></i>market</span>'
             '<span class="l-bl"><i></i>blend</span></div>')


def _gm_row(label, model, market, blend):
    """One goals-market bar row (model bar + market bar + blend tick). None model -> skip."""
    if model is None:
        return None
    mkt_bar = (f'<span class="gmbar mkt" style="width:{market * 100:.0f}%" '
               f'title="market {pct(market)}"></span>' if market is not None else "")
    tick = (f'<span class="gmtick" style="left:{blend * 100:.0f}%" '
            f'title="blend {pct(blend)}"></span>' if blend is not None else "")
    mkt_val = pct(market) if market is not None else "&mdash;"
    return (f'<div class="gmrow"><span class="gmlabel">{label}</span>'
            f'<span class="gmtrack">'
            f'<span class="gmbar mdl" style="width:{model * 100:.0f}%" '
            f'title="model {pct(model)}"></span>{mkt_bar}{tick}</span>'
            f'<span class="gmvals"><span class="num">{pct(model)}</span>'
            f'<span class="num gm-mkt">{mkt_val}</span></span></div>')


def goals_markets_panel(m):
    ex = m.get("extras") or {}
    ta, tb = m["teams"]
    rows = []
    btts = ex.get("btts") or {}
    if btts.get("model") is not None:
        rows.append(_gm_row("Both score", btts.get("model"),
                            btts.get("market"), btts.get("blend")))
    for line, t in (ex.get("totals") or {}).items():
        t = t or {}
        r = _gm_row(f"Over {line}", t.get("model_over"),
                    t.get("market_over"), t.get("blend_over"))
        if r:
            rows.append(r)
    rows = [r for r in rows if r]

    scorelines = ex.get("scorelines") or []
    sc_html = ""
    if scorelines:
        smax = max((p for _, p in scorelines), default=1) or 1
        sc_rows = "".join(
            f'<div class="scrow"><span class="sclab num">{escape(str(s))}</span>'
            f'<span class="sctrack"><span class="scbar" '
            f'style="width:{p / smax * 100:.0f}%"></span></span>'
            f'<span class="scval num">{pct(p)}</span></div>'
            for s, p in scorelines)
        sc_html = (f'<div class="gm-scores"><div class="gm-sc-h">Most likely scores</div>'
                   f'{sc_rows}</div>')

    if not rows and not sc_html:
        return ""
    body = f'{GM_LEGEND}{"".join(rows)}{sc_html}'
    mp = round(d["blend_weight_model"] * 100)
    return panel(f'{escape(ta)} v {escape(tb)} &middot; goals markets', body, span=6,
                 note='Model (green) vs de-vigged market (magenta); tick marks the '
                      f'published {mp}/{100 - mp} blend. A missing bar/tick means the '
                      'books had not priced that line.')


def player_props_panel(m):
    ex = m.get("extras") or {}
    ta, tb = m["teams"]
    players = ex.get("players") or []
    rows = []
    for p in players:
        sc = p.get("p_score")
        if sc is None:                       # no model scorer prob -> drop row
            continue
        mkt = p.get("p_score_mkt")
        tick = (f'<span class="pptick" style="left:{mkt * 100:.0f}%" '
                f'title="market {pct(mkt)}"></span>' if mkt is not None else "")
        mkt_val = pct(mkt) if mkt is not None else "&mdash;"
        ast = p.get("p_assist")
        ast_val = pct(ast) if ast is not None else "&mdash;"
        rows.append(
            f'<tr><td class="pp-name">{escape(p.get("player", "?"))}'
            f'<span class="pp-team">{escape(p.get("team", ""))}</span></td>'
            f'<td class="num">{p.get("goals", 0)} / {p.get("assists", 0)}</td>'
            f'<td><span class="ppscore"><span class="pptrack">'
            f'<span class="ppbar" style="width:{sc * 100:.0f}%" '
            f'title="model {pct(sc)}"></span>{tick}</span>'
            f'<span class="ppnums"><span class="num">{pct(sc)}</span>'
            f'<span class="num gm-mkt">{mkt_val}</span></span></span></td>'
            f'<td class="num">{ast_val}</td></tr>')
    if not rows:
        return ""
    legend = ('<div class="gm-legend" aria-hidden="true">'
              '<span class="l-mdl"><i></i>model</span>'
              '<span class="l-mkt-tick"><i></i>market</span></div>')
    body = (f'{legend}<div class="tablewrap"><table class="pp-t">'
            '<thead><tr><th>Player</th><th>G / A</th>'
            '<th>Anytime scorer</th><th>Assist</th></tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table></div>')
    return panel(f'{escape(ta)} v {escape(tb)} &middot; player props', body, span=6,
                 note='Market implied probs keep the bookmaker margin; shares assume '
                      'the player starts. Assist column is model-only where unquoted.')


extras_panels = []
for m in d["matches"]:
    if not m.get("extras"):
        continue
    for p in (goals_markets_panel(m), player_props_panel(m)):
        if p:
            extras_panels.append(p)
extras_html = "\n".join(extras_panels)

# ============================================================ 4. calibration
retro = d["retro"]
hits = sum(1 for r in retro if r["called"] == "yes")
calib_svg = charts.calibration_chart(retro)
strip, table_rows = [], []
for r in retro:
    hit = r["called"] == "yes"
    title = (f'{fmt_date(r["date"])} &middot; {r["match"]} &middot; model {r["model_WDL"]} '
             f'&middot; result {r["actual"]} &middot; {"called" if hit else "missed"}')
    strip.append(f'<span class="cell{"" if hit else " miss"}" title="{title}"></span>')
    table_rows.append(
        f'<tr class="{"hit" if hit else "miss"}"><td>{fmt_date(r["date"])}</td>'
        f'<td>{r["match"]}</td><td class="num">{r["model_WDL"]}</td>'
        f'<td class="num">{r["actual"]}</td>'
        f'<td><span class="{"yes" if hit else "no"}">{"called" if hit else "missed"}</span></td></tr>'
    )

# ------------------------------------------------------------- goals + elo
g = d["goals_2026"]
per_game = {t: (v["scored"] / v["games"], v["conceded"] / v["games"]) for t, v in g.items()}
max_spg = max((s for s, _ in per_game.values()), default=1)
max_cpg = max((c for _, c in per_game.values()), default=1)


def mini_rows(idx, max_v, ascending=False):
    order = sorted(per_game.items(), key=lambda kv: kv[1][idx] if ascending else -kv[1][idx])
    out = []
    for team, vals in order:
        v = vals[idx]
        out.append(
            f'<div class="mrow"><span class="mteam">{team}</span>'
            f'<span class="mtrack"><span class="mbar" style="width:{v / max_v * 100:.0f}%"></span></span>'
            f'<span class="mval">{v:.2f}</span></div>'
        )
    return "\n".join(out)


SEMIFINALISTS = set(g.keys())
elo_rows = []
for i, (team, elo) in enumerate(sorted(d["elo_top"].items(), key=lambda kv: -kv[1]), 1):
    cls = ' class="fournations"' if team in SEMIFINALISTS else ""
    elo_rows.append(f'<tr{cls}><td>{i}</td><td>{team}</td><td class="num">{elo:.0f}</td></tr>')

# ------------------------------------------------------------------ KPI row
def kpi_tile(value, label):
    return (f'<div class="kpi-tile"><div class="kpi-val">{value}</div>'
            f'<div class="kpi-lab">{label}</div></div>')


kpi = []
if win_src:                                    # tournament favourite
    fav_team, fav_p = max(win_src.items(), key=lambda kv: kv[1])
    kpi.append(kpi_tile(pct(fav_p, 0), f"Favourite &middot; {fav_team}"))
if div_big_pts is not None:                    # biggest model-market gap
    kpi.append(kpi_tile(f"{div_big_pts:+.1f}<small>pts</small>",
                        f"Biggest gap &middot; {div_lbl}"))
if retro:                                      # calibration hit rate
    kpi.append(kpi_tile(f"{hits / len(retro) * 100:.0f}<small>%</small>",
                        f"Calibration &middot; {hits}/{len(retro)} called"))
if odds_snaps:                                 # odds coverage
    kpi.append(kpi_tile(str(len(odds_snaps)),
                        f'Snapshots &middot; ~{odds_snaps[0]["books"]} books'))

# --------------------------------------------------------------------- render
gen = datetime.fromisoformat(d["generated_utc"])
model_pct = round(d["blend_weight_model"] * 100)

# method chip carries the model version when present (falls back to the plain form)
mv = d.get("model_version")
if mv:
    method_chip = (f'model {mv} &middot; Elo+offsets Poisson &middot; '
                   f'blend {model_pct}/{100 - model_pct} with market')
else:
    method_chip = f'Elo + Poisson &middot; blend {model_pct}/{100 - model_pct} with market'
# footer note about the offsets layer + V1 numbers kept in the payload
has_v1 = any(m.get("model_v1") for m in d["matches"])
v2_note = (' The V2 model adds a per-team goal-offset layer on top of Elo before the '
           'Poisson step; the Elo-only V1 numbers are retained in the data payload below.'
           if mv and has_v1 else "")

tokens = {
    "GENERATED_HUMAN": gen.strftime("%d %b %Y, %H:%M UTC").lstrip("0"),
    "GENERATED_ISO": d["generated_utc"],
    "METHOD_CHIP": method_chip,
    "V2_NOTE": v2_note,
    "MODEL_PCT": str(model_pct),
    "MKT_PCT": str(100 - model_pct),
    "EXTRAS_PANELS": extras_html,
    "KPI_TILES": "\n".join(kpi),
    "WINNER_CHART": winner_svg,
    "WINNER_NOTE": winner_note,
    "WINNER_TABLE_ROWS": win_tbl_rows,
    "FEATURED_WDL_PANEL": featured_wdl_panel,
    "DIVERGENCE_PANEL": divergence_panel,
    "TIMELINE_PANEL": timeline_panel,
    "FIXTURE_ROWS": "\n".join(fixture_rows),
    "FIXTURES_NOTE": fixtures_note,
    "CALIB_CHART": calib_svg,
    "HIT_COUNT": str(hits),
    "RETRO_N": str(len(retro)),
    "HIT_RATE": f"{hits / len(retro) * 100:.0f}" if retro else "0",
    "RETRO_STRIP": "\n".join(strip),
    "RETRO_ROWS": "\n".join(table_rows),
    "SCORED_ROWS": mini_rows(0, max_spg),
    "CONCEDED_ROWS": mini_rows(1, max_cpg, ascending=True),
    "ELO_ROWS": "\n".join(elo_rows),
    "DATA_JSON": json.dumps(d, separators=(",", ":")),
}

html = (HERE / "template.html").read_text(encoding="utf-8")
for k, v in tokens.items():
    html = html.replace("{{" + k + "}}", v)

leftover = re.findall(r"\{\{[A-Z_]+\}\}", html)
assert not leftover, f"unreplaced tokens: {leftover}"

out = HERE / "index.html"
out.write_text(html, encoding="utf-8")
print(f"wrote {out} ({len(html):,} chars, {hits}/{len(retro)} calls, "
      f"{'featured+' if featured else 'no-featured, '}{len(odds_snaps)} odds snapshots)")
