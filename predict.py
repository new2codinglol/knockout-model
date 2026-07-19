"""WC2026 predictions: remaining matches, tournament winner probs, market comparison,
and a retrodiction of the knockout rounds played so far. Prints markdown, saves
data/predictions.csv.
"""
import json
import unicodedata

import numpy as np
import pandas as pd

import odds as market_mod
import players as players_mod
from model import (derived_markets, elo_expectancy, fit_offsets, fit_poisson,
                   load_matches, match_probs, training_frame)

DATA_OUT = "data/predictions.csv"
W_MODEL = 0.30  # ponytail: blend weight not fit (no historical WC odds); refit once odds_history.csv spans a tournament

REMAINING = [
    # (team_a, team_b, date, label, prior = P(this pairing happens))
    # tournament complete — Spain won the Final 1-0 aet (Jul 19, 2026)
]


def market_probs(market, team_a, team_b):
    """Market consensus from team A's perspective, or None."""
    if market is None:
        return None
    for r in market.itertuples():
        if {r.home_team, r.away_team} == {team_a, team_b}:
            if r.home_team == team_a:
                return {"win": r.p_home, "draw": r.p_draw, "loss": r.p_away}
            return {"win": r.p_away, "draw": r.p_draw, "loss": r.p_home}
    return None


def blend(model_p, mkt_p):
    if mkt_p is None:
        return None
    b = {k: W_MODEL * model_p[k] + (1 - W_MODEL) * mkt_p[k] for k in ("win", "draw", "loss")}
    s = sum(b.values())
    return {k: v / s for k, v in b.items()}


def fmt(p):
    return f"{p['win']:.1%} / {p['draw']:.1%} / {p['loss']:.1%}" if p else "-"


NEUTRAL_OFF = {"atk": 1.0, "def": 1.0}


def _norm(name):
    s = unicodedata.normalize("NFD", name).encode("ascii", "ignore").decode()
    return s.casefold()


def _market_prob(name, table):
    """Implied prob for a player, tolerant of naming drift (accents, extra surname)."""
    want = set(_norm(name).split())
    for k, v in table.items():
        have = set(_norm(k).split())
        if want <= have or have <= want:
            return v
    return None


def main():
    matches = load_matches()
    params = fit_poisson(training_frame(matches))
    elo = pd.read_csv("data/current_elo.csv", index_col="team").elo

    market = market_mod.get_market()
    steam = market_mod.steam_notes()

    # --- V2 layers: goal offsets, extra-market odds, player stats ---
    offsets = fit_offsets(matches, params)
    extras_mkt = market_mod.extras_consensus([(a, b) for a, b, *_ in REMAINING])
    pstats = players_mod.load_stats()

    # tournament goals for/against (site minis + prop share denominators)
    wc26 = matches.dropna(subset=["home_score"])
    wc26 = wc26[(wc26.tournament == "FIFA World Cup") & (wc26.date.dt.year == 2026)]
    goals = {}
    for t in ("Spain", "Argentina", "England", "France"):
        h, aw = wc26[wc26.home_team == t], wc26[wc26.away_team == t]
        goals[t] = {"games": len(h) + len(aw),
                    "scored": int(h.home_score.sum() + aw.away_score.sum()),
                    "conceded": int(h.away_score.sum() + aw.home_score.sum())}

    # --- remaining bracket (post-semi: both pairings are certain) ---
    fixtures = REMAINING

    rows, site_matches = [], []
    for a, b, date, label, prior in fixtures:
        p1 = match_probs(elo[a], elo[b], params, knockout=True)  # V1: Elo only
        p = match_probs(elo[a], elo[b], params, knockout=True,   # V2: + goal offsets
                        offsets=(offsets.get(a, NEUTRAL_OFF), offsets.get(b, NEUTRAL_OFF)))
        mkt = market_probs(market, a, b)
        bl = blend(p, mkt)
        note = steam.get((a, b)) or steam.get((b, a), "")
        rows.append({"match": f"{a} v {b}", "date": date, "label": label, "p_pairing": prior,
                     "V1_WDL": fmt(p1), "V2_WDL": fmt(p), "model_advance": p["advance"],
                     "market_WDL": fmt(mkt),
                     "blend_WDL": fmt(bl),
                     "divergence_win": (p["win"] - mkt["win"]) if mkt else np.nan,
                     "steam": note})

        # extras: grid-derived markets + player props, market alongside
        der = derived_markets(p["lam_a"], p["lam_b"])
        me = extras_mkt.get(frozenset((a, b)), {})
        btts_mkt = me.get("btts_yes")
        totals = {}
        for line, ou in der["totals"].items():
            mo = (me.get("totals") or {}).get(line)
            totals[str(line)] = {
                "model_over": round(ou["over"], 4),
                "market_over": round(mo, 4) if mo is not None else None,
                "blend_over": (round(W_MODEL * ou["over"] + (1 - W_MODEL) * mo, 4)
                               if mo is not None else None)}
        players_out = []
        if pstats is not None:
            for team, lam in ((a, p["lam_a"]), (b, p["lam_b"])):
                for pr in players_mod.team_props(pstats, team, lam,
                                                 goals.get(team, {}).get("scored", 0)):
                    pr["p_score_mkt"] = _market_prob(pr["player"], me.get("scorer", {}))
                    pr["p_assist_mkt"] = _market_prob(pr["player"], me.get("assists", {}))
                    players_out.append({k: (round(v, 4) if isinstance(v, float) else v)
                                        for k, v in pr.items()})
        extras = {
            "btts": {"model": round(der["btts"], 4),
                     "market": round(btts_mkt, 4) if btts_mkt is not None else None,
                     "blend": (round(W_MODEL * der["btts"] + (1 - W_MODEL) * btts_mkt, 4)
                               if btts_mkt is not None else None)},
            "totals": totals,
            "scorelines": [[s, round(pr_, 4)] for s, pr_ in der["scorelines"]],
            "players": players_out,
        }

        pens = 0.5 + (elo_expectancy(elo[a] - elo[b]) - 0.5) / 3
        site_matches.append({
            "teams": [a, b], "date": date, "label": label, "p_pairing": round(prior, 4),
            "model": {k: round(p[k], 4) for k in ("win", "draw", "loss")},
            "xg": {a: round(float(p["lam_a"]), 2), b: round(float(p["lam_b"]), 2)},
            "model_v1": {k: round(p1[k], 4) for k in ("win", "draw", "loss")},
            "model_advance": round(p["advance"], 4),
            "market": {k: round(mkt[k], 4) for k in ("win", "draw", "loss")} if mkt else None,
            "blend": {k: round(bl[k], 4) for k in ("win", "draw", "loss")} if bl else None,
            "blend_advance": round(bl["win"] + bl["draw"] * pens, 4) if bl else None,
            "divergence_win": round(p["win"] - mkt["win"], 4) if mkt else None,
            "steam": note,
            "extras": extras})

    out = pd.DataFrame(rows)
    if len(out):
        print("## Remaining matches (probs are first-named team's Win/Draw/Loss in 90'; "
              "V2 = Elo + goal offsets)\n")
        print(out.drop(columns="p_pairing").to_markdown(index=False, floatfmt=".3f"))
    else:
        print("## Tournament complete — Spain are 2026 world champions (1-0 aet v Argentina)")

    print("\n## Extras (V2 model vs market)\n")
    for m in site_matches:
        a, b = m["teams"]
        e = m["extras"]
        mb = e["btts"]
        line = f"- **{a} v {b}** — BTTS yes: model {mb['model']:.1%}"
        if mb["market"] is not None:
            line += f" / market {mb['market']:.1%}"
        for ln, ou in sorted(e["totals"].items(), key=lambda kv: float(kv[0])):
            line += f"; O{ln}: model {ou['model_over']:.1%}"
            if ou["market_over"] is not None:
                line += f" / market {ou['market_over']:.1%}"
        top = ", ".join(f"{s} {pr_:.1%}" for s, pr_ in e["scorelines"][:3])
        print(line + f"; top scores: {top}")
        for pr in e["players"]:
            mkt_s = f" (mkt {pr['p_score_mkt']:.1%})" if pr["p_score_mkt"] else ""
            print(f"    {pr['player']:24s} score {pr['p_score']:.1%}{mkt_s}  "
                  f"assist {pr['p_assist']:.1%}")

    # --- tournament winner: decided on the pitch ---
    print("\n## Tournament winner\n")
    winners = pd.Series({"Spain": 1.0, "Argentina": 0.0})
    print(winners.map("{:.1%}".format).to_string())
    winners_blend = {"Spain": 1.0, "Argentina": 0.0}

    # --- retrodiction: 2026 knockout rounds already played ---
    ko = matches.dropna(subset=["home_score"])
    ko = ko[(ko.tournament == "FIFA World Cup") & (ko.date >= "2026-06-28")]
    retro = []
    for m in ko.itertuples():
        p = match_probs(m.home_elo, m.away_elo, params, neutral=m.neutral)
        score = f"{int(m.home_score)}-{int(m.away_score)}"
        if m.home_score == m.away_score:
            score += " (pens)"  # ponytail: shootout winner lives in upstream shootouts.csv, not fetched
        picked = max(("win", "draw", "loss"), key=lambda k: p[k])
        actual = "win" if m.home_score > m.away_score else "loss" if m.home_score < m.away_score else "draw"
        retro.append({"date": m.date.date(), "match": f"{m.home_team} v {m.away_team}",
                      "model_WDL": fmt(p), "actual": score,
                      "p_win": round(p["win"], 4), "p_draw": round(p["draw"], 4),
                      "p_loss": round(p["loss"], 4),
                      "called": "yes" if picked == actual else "no"})
    retro = pd.DataFrame(retro)
    print(f"\n## 2026 knockout retrodiction ({(retro.called == 'yes').mean():.0%} of "
          f"{len(retro)} matches called by modal outcome)\n")
    print(retro.to_markdown(index=False))

    out.to_csv(DATA_OUT, index=False)

    # --- JSON payload for the website ---
    site = {
        "generated_utc": pd.Timestamp.now(tz="UTC").isoformat(timespec="seconds"),
        "model_version": "V2",
        "matches": site_matches,
        "winner_model": {k: round(v, 4) for k, v in winners.items()},
        "winner_blend": {k: round(v, 4) for k, v in winners_blend.items()} if winners_blend else None,
        "retro": [{**r, "date": str(r["date"])} for r in retro.to_dict("records")],
        "elo_top": pd.read_csv("data/current_elo.csv", index_col="team").elo.head(12).round(0).to_dict(),
        "goals_2026": goals,
        "blend_weight_model": W_MODEL,
    }
    with open("data/site_data.json", "w") as f:
        json.dump(site, f, indent=1)

    if market is None:
        print("\nNOTE: no market data (set ODDS_API_KEY or fill data/manual_odds.csv) - "
              "market/blend/divergence columns empty.")
    print("\nfull report: python report.py   ·   site: python site/build.py")


if __name__ == "__main__":
    main()
