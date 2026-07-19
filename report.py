"""Scrollable terminal report of the WC2026 model — one section per remaining
game (the Final first), each with W/D/L, line movement, goals markets, player
props and the model-vs-books EDGES. A pure renderer over data/site_data.json:

    python report.py

Colors auto-disable when piped or NO_COLOR is set.
"""
import csv
import json
import os
import statistics
import sys
from pathlib import Path

DATA = Path(__file__).parent / "data"
EDGE_MIN = 0.03  # flag model-vs-books gaps of 3+ points

os.system("")  # enable ANSI escape processing on Windows conhost
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")


def c(code, s):
    return f"\033[{code}m{s}\033[0m" if COLOR else str(s)


def GRN(s): return c("32", s)
def MAG(s): return c("35", s)
def RED(s): return c("31", s)
def DIM(s): return c("2", s)
def BOLD(s): return c("1", s)


SPARK = "▁▂▃▄▅▆▇█"
SEG_A, SEG_D, SEG_B = ("█", "█", "█") if COLOR else ("█", "▒", "░")


def pct(x, dp=1):
    return f"{x * 100:.{dp}f}%"


def mpct(x, dp=1):
    return pct(x, dp) if x is not None else "—"


def bar(p, width=30, color=GRN):
    n = round(p * width)
    return color("█" * n) + DIM("·" * (width - n))


def seg_bar(probs, width=46):
    wa = round(probs["win"] * width)
    wd = round(probs["draw"] * width)
    return (GRN(SEG_A * wa) + DIM(SEG_D * wd)
            + MAG(SEG_B * max(width - wa - wd, 0)))


def spark(vals):
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    return "".join(SPARK[min(int((v - lo) / span * (len(SPARK) - 1)), len(SPARK) - 1)]
                   for v in vals)


def h(title, big=False):
    print()
    if big:
        line = "═" * 64
        print(GRN(line))
        print(GRN("  ") + BOLD(title.upper()))
        print(GRN(line))
    else:
        print(GRN("| ") + BOLD(title.upper()))
        print(DIM("─" * 64))


def movement(ta, tb):
    """Per-snapshot de-vigged consensus for a pairing, from odds_history.csv.

    ponytail: duplicated from site/build.py:load_odds (importing that module
    runs the whole site build).
    """
    hist = DATA / "odds_history.csv"
    if not hist.exists():
        return []
    groups = {}
    for r in csv.DictReader(hist.read_text(encoding="utf-8").splitlines()):
        if {r["home_team"], r["away_team"]} != {ta, tb}:
            continue
        try:
            oh, od, oa = float(r["home_odds"]), float(r["draw_odds"]), float(r["away_odds"])
        except (ValueError, KeyError):
            continue
        if r["home_team"] != ta:
            oh, oa = oa, oh
        s = 1 / oh + 1 / od + 1 / oa
        groups.setdefault(r["fetched_at"], []).append((1 / oh / s, 1 / od / s, 1 / oa / s))
    return [tuple(statistics.median(x[i] for x in g) for i in range(3))
            for _, g in sorted(groups.items())]


def edge_rows(m):
    """Two tiers of (label, model, market) rows disagreeing ≥ EDGE_MIN:
    solid (match result + goals markets, both sides de-vigged) and
    rough (player props — share-based model vs still-vigged prices)."""
    solid, rough = [], []
    if m.get("market"):
        a, b = m["teams"]
        for lbl, k in ((f"{a} win", "win"), ("Draw", "draw"), (f"{b} win", "loss")):
            solid.append((lbl, m["model"][k], m["market"][k]))
    e = m.get("extras") or {}
    if e.get("btts") and e["btts"].get("market") is not None:
        solid.append(("Both teams score", e["btts"]["model"], e["btts"]["market"]))
    for line, ou in sorted((e.get("totals") or {}).items(), key=lambda kv: float(kv[0])):
        if ou.get("market_over") is not None:
            solid.append((f"Over {line} goals", ou["model_over"], ou["market_over"]))
    for p in e.get("players") or []:
        if p.get("p_score_mkt") is not None:
            rough.append((f"{p['player']} scores", p["p_score"], p["p_score_mkt"]))
    keep = lambda rows: sorted((r for r in rows if abs(r[1] - r[2]) >= EDGE_MIN),
                               key=lambda r: -abs(r[1] - r[2]))
    return keep(solid), keep(rough)


def match_section(m, ver):
    a, b = m["teams"]
    kind = "THE FINAL" if m["label"] == "Final" else m["label"]
    h(f"{kind} · {a} v {b} · {m['date']}", big=True)

    # --- 90-min probabilities ---
    print(DIM(f"  {GRN(SEG_A)} {a} win   {DIM(SEG_D)} draw   {MAG(SEG_B)} {b} win"))
    rows = [("Model" + (" V2" if ver else ""), m["model"], m.get("model_advance"))]
    if m.get("market"):
        rows.append(("Books (de-vigged)", m["market"], None))
    if m.get("blend"):
        rows.append(("Published blend", m["blend"], m.get("blend_advance")))
    for name, probs, adv in rows:
        adv_s = DIM(f"  → {b} through {pct(1 - adv)}") if adv is not None else ""
        print(f"  {name:<18} {seg_bar(probs)}  "
              f"{pct(probs['win'])} / {pct(probs['draw'])} / {pct(probs['loss'])}{adv_s}")
    if m.get("xg"):
        print("  " + BOLD("expected goals") + "     "
              + DIM(" · ").join(f"{t} {GRN(f'{x:.2f}')}" for t, x in m["xg"].items()))
    if m.get("model_v1"):
        v1 = m["model_v1"]
        print(DIM(f"  {'Elo-only (V1)':<18} would say {pct(v1['win'])} / "
                  f"{pct(v1['draw'])} / {pct(v1['loss'])} — the offsets layer is the difference"))

    # --- line movement ---
    snaps = movement(a, b)
    if len(snaps) >= 2:
        print()
        print("  " + BOLD("line movement") + DIM(f"  ({len(snaps)} snapshots)"))
        for i, (lbl, col) in enumerate(((f"{a} win", GRN), ("draw", DIM), (f"{b} win", MAG))):
            vals = [s[i] for s in snaps]
            print(f"    {lbl:<14} {col(spark(vals))}  {pct(vals[0])} → {BOLD(pct(vals[-1]))}")

    # --- goals markets ---
    e = m.get("extras") or {}
    market_rows = []
    if e.get("btts"):
        bt = e["btts"]
        market_rows.append(("Both teams score", bt["model"], bt["market"], bt["blend"]))
    for line, ou in sorted((e.get("totals") or {}).items(), key=lambda kv: float(kv[0])):
        market_rows.append((f"Over {line} goals", ou["model_over"], ou["market_over"], ou["blend_over"]))
    if market_rows:
        print()
        print("  " + BOLD("goals markets") + DIM("        model   books   blend"))
        for lbl, pm, pk, bl in market_rows:
            print(f"    {lbl:<19} {GRN(f'{pct(pm):>6}')}  {mpct(pk):>6}  {mpct(bl):>6}")
    if e.get("scorelines"):
        print(DIM("    most likely scores  ")
              + "   ".join(f"{s} {DIM(pct(p))}" for s, p in e["scorelines"]))

    # --- player props ---
    players = e.get("players") or []
    if players:
        print()
        print("  " + BOLD("anytime scorer / assist")
              + DIM("                 score            assist"))
        print(DIM(f"    {'player':<24}{'G/A':>5}    {'model':>6} {'books':>6}    {'model':>6} {'books':>6}"))
        for p in players:
            sc = f"{pct(p['p_score']):>6}"
            print(f"    {p['player']:<24}{p['goals']}/{p['assists']:>2}    "
                  f"{GRN(sc)} {mpct(p.get('p_score_mkt')):>6}    "
                  f"{pct(p['p_assist']):>6} {mpct(p.get('p_assist_mkt')):>6}")
        print(DIM("    props assume the player starts; books' prop prices keep the vig"))

    # --- edges ---
    solid, rough = edge_rows(m)

    def edge_line(lbl, pm, pk):
        diff = (pm - pk) * 100
        arrow = GRN("▲ model higher") if diff > 0 else MAG("▼ books higher")
        fair = DIM(f"fair odds {1 / pm:.2f} vs books {1 / pk:.2f}")
        print(f"    {lbl:<26} model {pct(pm):>6} vs {pct(pk):>6}  "
              f"{diff:+5.1f} pts  {arrow}  {fair}")

    if solid or rough:
        print()
        print("  " + BOLD(GRN("EDGES")) + DIM(f"  where model and books disagree by ≥{EDGE_MIN * 100:.0f} pts"))
        for lbl, pm, pk in solid:
            edge_line(lbl, pm, pk)
        if rough:
            print(DIM("    — player props (rough: share-based model, vigged prices) —"))
            for lbl, pm, pk in rough:
                edge_line(lbl, pm, pk)
        print(DIM("    ▲ = model sees value backing it (worth a price check); "
                  "▼ = books rate it higher than the model"))
    elif m.get("market"):
        print()
        print(DIM("  no edges ≥3 pts — model and books broadly agree here"))


# ============================================================== render
d = json.loads((DATA / "site_data.json").read_text(encoding="utf-8"))
ver = d.get("model_version", "")
model_pct = round(d.get("blend_weight_model", 0.3) * 100)

print(BOLD("THE KNOCKOUT MODEL") + (f"  {GRN('· ' + ver)}" if ver else "")
      + DIM(f"  ·  Elo{'+offsets' if ver == 'V2' else ''} Poisson · blend "
            f"{model_pct}/{100 - model_pct} with market"))
print(DIM(f"data {d['generated_utc']} · World Cup 2026 knockout stage · not betting advice"))

# --- tournament winner ---
h("Chance of winning the tournament")
src = d.get("winner_blend") or d["winner_model"]
blended = bool(d.get("winner_blend"))
for team, p in sorted(src.items(), key=lambda kv: -kv[1]):
    extra = DIM(f"  model {pct(d['winner_model'][team])}") if blended else ""
    print(f"  {team:<12} {bar(p)} {BOLD(pct(p)):>6}{extra}")
print(DIM(f"  bar: published blend ({100 - model_pct}% books / {model_pct}% model)"
          if blended else "  model-only (no market blend available)"))

# --- the model's picks ---
h("The model's picks")
mdl = d["winner_model"]
fav = max(mdl, key=mdl.get)
fav_blend = (d.get("winner_blend") or mdl)[fav]
print(f"  {'Tournament':<12} {BOLD(fav + ' lift the trophy'):<44} "
      f"{pct(mdl[fav])} model · {pct(fav_blend)} blend")

for m in sorted(d["matches"], key=lambda m: 0 if m["label"] == "Final" else 1):
    a, b = m["teams"]
    p = m["model"]
    e = m.get("extras") or {}
    print()
    print(f"  {BOLD(('THE FINAL' if m['label'] == 'Final' else m['label']).upper())}"
          + DIM(f" · {a} v {b} · {m['date']}"))

    def pick(label, call, prob, vs=None):
        vs_s = DIM(f"  (books {pct(vs)})") if vs is not None else ""
        print(f"    {label:<10} {call:<42} {pct(prob)}{vs_s}")

    res = max(("win", "draw", "loss"), key=lambda k: p[k])
    res_call = {"win": f"{a} win in 90'", "draw": "Draw in 90'", "loss": f"{b} win in 90'"}[res]
    pick("Result", res_call, p[res], (m.get("market") or {}).get(res))
    adv = m["model_advance"]
    side, padv = (a, adv) if adv >= 0.5 else (b, 1 - adv)
    through = "lift the trophy" if m["label"] == "Final" else "take 3rd place"
    pick("Winner", f"{side} {through} (ET/pens counted)", padv)
    if e.get("scorelines"):
        s, sp = e["scorelines"][0]
        pick("Score", s, sp)
    ou25 = (e.get("totals") or {}).get("2.5")
    if ou25:
        over = ou25["model_over"]
        pick("Goals", "Over 2.5" if over >= 0.5 else "Under 2.5",
             max(over, 1 - over),
             (ou25["market_over"] if over >= 0.5 else 1 - ou25["market_over"])
             if ou25.get("market_over") is not None else None)
    if e.get("btts"):
        by = e["btts"]["model"]
        pick("BTTS", "Yes" if by >= 0.5 else "No", max(by, 1 - by),
             (e["btts"]["market"] if by >= 0.5 else 1 - e["btts"]["market"])
             if e["btts"].get("market") is not None else None)
    players = e.get("players") or []
    if players:
        top = max(players, key=lambda q: q["p_score"])
        pick("Scorer", f"{top['player']} anytime", top["p_score"], top.get("p_score_mkt"))

    solid, _ = edge_rows(m)
    value = [(lbl, pm, pk) for lbl, pm, pk in solid if pm > pk]
    if value:
        for lbl, pm, pk in value:
            print(f"    {'Value':<10} {GRN(f'{lbl} — worth backing at {1 / pm:.2f} or better'):<52} "
                  f"{DIM(f'+{(pm - pk) * 100:.1f} pts on the books')}")
    elif m.get("market"):
        print(DIM(f"    {'Value':<10} none — the books price this one at or above the model"))
print(DIM("\n  picks = the model's modal call per market; value = solid edges where "
          "the model is above the books"))

# --- one section per remaining game, the Final first ---
for m in sorted(d["matches"], key=lambda m: 0 if m["label"] == "Final" else 1):
    match_section(m, ver)

# --- calibration ---
retro = d.get("retro") or []
if retro:
    hits = sum(1 for r in retro if r["called"] == "yes")
    h(f"Track record · {hits} of {len(retro)} knockout games called "
      f"({hits / len(retro) * 100:.0f}%)")
    print("  " + "".join(GRN("■") if r["called"] == "yes" else RED("□") for r in retro))
    print(DIM("  one cell per match, in order played — filled green called, open red missed\n"))
    print(DIM(f"  {'date':<12}{'match':<42}{'model W/D/L':<24}{'result':<12}called"))
    for r in retro:
        mark = GRN("called") if r["called"] == "yes" else RED("missed")
        print(f"  {r['date']:<12}{r['match']:<42}{r['model_WDL']:<24}{r['actual']:<12}{mark}")

# --- Elo ---
if d.get("elo_top"):
    h("Current Elo · top 12")
    semis = set((d.get("goals_2026") or {}).keys())
    for i, (team, elo) in enumerate(sorted(d["elo_top"].items(), key=lambda kv: -kv[1]), 1):
        star = GRN(" ●") if team in semis else ""
        print(f"  {i:>2}  {team:<18} {elo:.0f}{star}")
    print(DIM("  ● = still playing"))

# --- footer ---
print()
print(DIM(f"Method: Elo (~49,500 internationals) → Poisson goal model"
          + (" × per-team attack/defence offsets (V2)" if ver == "V2" else "")
          + f"; blended {model_pct}/{100 - model_pct} with de-vigged books."))
print(DIM("An edge is a disagreement, not a guarantee — a 60% favourite still "
          "loses two times in five."))
