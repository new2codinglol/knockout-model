"""Bookmaker odds: fetch from The Odds API (needs ODDS_API_KEY env var, free tier),
snapshot every run to data/odds_history.csv (line-movement log), de-vig and build a
Pinnacle-weighted consensus. Falls back to the last snapshot, then data/manual_odds.csv.
"""
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

DATA = Path(__file__).parent / "data"
HISTORY = DATA / "odds_history.csv"
MANUAL = DATA / "manual_odds.csv"
API = "https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds"
PINNACLE_WEIGHT = 2.0

MANUAL_TEMPLATE = """home_team,away_team,book,home_odds,draw_odds,away_odds
# England,Argentina,pinnacle,3.10,3.30,2.45   <- example: replace with real odds, delete the #
"""


def fetch_snapshot() -> pd.DataFrame | None:
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        return None
    r = requests.get(API, params={"apiKey": key, "regions": "us,uk,eu",
                                  "markets": "h2h", "oddsFormat": "decimal"}, timeout=30)
    r.raise_for_status()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for game in r.json():
        for book in game["bookmakers"]:
            h2h = next((m for m in book["markets"] if m["key"] == "h2h"), None)
            if not h2h:
                continue
            prices = {o["name"]: o["price"] for o in h2h["outcomes"]}
            rows.append({"fetched_at": now, "commence": game["commence_time"],
                         "home_team": game["home_team"], "away_team": game["away_team"],
                         "book": book["key"], "home_odds": prices.get(game["home_team"]),
                         "draw_odds": prices.get("Draw"), "away_odds": prices.get(game["away_team"])})
    snap = pd.DataFrame(rows).dropna()
    if len(snap):
        snap.to_csv(HISTORY, mode="a", header=not HISTORY.exists(), index=False)
    return snap


def devig(row) -> tuple[float, float, float]:
    inv = 1 / row.home_odds, 1 / row.draw_odds, 1 / row.away_odds
    s = sum(inv)
    return inv[0] / s, inv[1] / s, inv[2] / s


def consensus(snap: pd.DataFrame) -> pd.DataFrame:
    """Per match: de-vigged, Pinnacle-weighted average probs + Pinnacle-vs-rest divergence."""
    out = []
    for (home, away), grp in snap.groupby(["home_team", "away_team"]):
        probs = pd.DataFrame([devig(r) for r in grp.itertuples()],
                             columns=["home", "draw", "away"], index=grp.book.values)
        w = pd.Series(1.0, index=probs.index).mask(probs.index.str.contains("pinnacle"), PINNACLE_WEIGHT)
        avg = probs.mul(w, axis=0).sum() / w.sum()
        pinn = probs[probs.index.str.contains("pinnacle")]
        pinn_gap = (pinn.home.mean() - probs.home.mean()) if len(pinn) else float("nan")
        out.append({"home_team": home, "away_team": away, "n_books": len(grp),
                    "p_home": avg.home, "p_draw": avg.draw, "p_away": avg.away,
                    "pinnacle_home_edge": pinn_gap})
    return pd.DataFrame(out)


def steam_notes() -> dict[tuple[str, str], str]:
    """Open->latest consensus drift per match from the snapshot history."""
    if not HISTORY.exists():
        return {}
    hist = pd.read_csv(HISTORY)
    notes = {}
    for (home, away), grp in hist.groupby(["home_team", "away_team"]):
        first = consensus(grp[grp.fetched_at == grp.fetched_at.min()]).iloc[0]
        last = consensus(grp[grp.fetched_at == grp.fetched_at.max()]).iloc[0]
        drift = last.p_home - first.p_home
        n = grp.fetched_at.nunique()
        if n > 1:
            notes[(home, away)] = f"home {first.p_home:.1%}->{last.p_home:.1%} ({drift:+.1%}, {n} snapshots)"
        else:
            notes[(home, away)] = "1 snapshot (rerun odds.py to track movement)"
    return notes


# ---------------------------------------------------------------- extras (V2)
EXTRAS_HISTORY = DATA / "odds_extras_history.csv"
EXTRA_MARKETS = "btts,totals,player_goal_scorer_anytime,player_assists"
EVENTS_API = API.rsplit("/", 1)[0] + "/events"


def fetch_extras(pairs) -> pd.DataFrame | None:
    """Snapshot btts/totals/player-prop odds for the given (a, b) pairings.

    One event-odds call per remaining match (markets x regions is what costs
    credits; the /events listing is free). Appends to odds_extras_history.csv.
    """
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        return None
    if EXTRAS_HISTORY.exists():  # reuse a recent snapshot instead of burning credits
        last = pd.read_csv(EXTRAS_HISTORY, usecols=["fetched_at"]).fetched_at.max()
        age = datetime.now(timezone.utc) - datetime.fromisoformat(last)
        if age.total_seconds() < 1800:
            return None
    events = requests.get(EVENTS_API, params={"apiKey": key}, timeout=30).json()
    want = [set(p) for p in pairs]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows, remaining = [], None
    for game in events:
        if {game["home_team"], game["away_team"]} not in want:
            continue
        r = requests.get(f"{EVENTS_API}/{game['id']}/odds",
                         params={"apiKey": key, "regions": "us,uk,eu",
                                 "markets": EXTRA_MARKETS, "oddsFormat": "decimal"},
                         timeout=30)
        r.raise_for_status()
        remaining = r.headers.get("x-requests-remaining", remaining)
        for book in r.json().get("bookmakers", []):
            for mkt in book["markets"]:
                for o in mkt["outcomes"]:
                    rows.append({
                        "fetched_at": now,
                        "home_team": game["home_team"], "away_team": game["away_team"],
                        "book": book["key"], "market": mkt["key"],
                        "outcome": o["name"], "player": o.get("description", ""),
                        "point": o.get("point", ""), "price": o["price"],
                    })
    if remaining is not None:
        print(f"extras fetched ({len(rows)} rows); Odds API credits remaining: {remaining}")
    snap = pd.DataFrame(rows)
    if len(snap):
        snap.to_csv(EXTRAS_HISTORY, mode="a", header=not EXTRAS_HISTORY.exists(), index=False)
    return snap


def extras_consensus(pairs) -> dict:
    """Latest extras snapshot -> per-pairing consensus.

    Returns {frozenset(pair): {"btts_yes": p, "totals": {point: p_over},
    "scorer": {player: implied}, "assists": {player: implied_over}}}.
    2-way markets are de-vigged per book then medianed; player props keep the
    vig (a 20-runner anytime-scorer book can't be cleanly de-vigged) and say so.
    """
    snap = fetch_extras(pairs)
    if (snap is None or not len(snap)) and EXTRAS_HISTORY.exists():
        hist = pd.read_csv(EXTRAS_HISTORY, keep_default_na=False)
        snap = hist[hist.fetched_at == hist.fetched_at.max()]
    if snap is None or not len(snap):
        return {}

    out = {}
    for (home, away), grp in snap.groupby(["home_team", "away_team"]):
        entry = {"btts_yes": None, "totals": {}, "scorer": {}, "assists": {}}

        btts = grp[grp.market == "btts"].pivot_table(
            index="book", columns="outcome", values="price", aggfunc="first")
        if {"Yes", "No"}.issubset(btts.columns):
            inv_y, inv_n = 1 / btts.Yes, 1 / btts.No
            entry["btts_yes"] = float(((inv_y) / (inv_y + inv_n)).median())

        tot = grp[grp.market == "totals"]
        for point, tg in tot.groupby("point"):
            piv = tg.pivot_table(index="book", columns="outcome", values="price", aggfunc="first")
            if {"Over", "Under"}.issubset(piv.columns):
                inv_o, inv_u = 1 / piv.Over, 1 / piv.Under
                entry["totals"][float(point)] = float((inv_o / (inv_o + inv_u)).median())

        for mkt, slot in (("player_goal_scorer_anytime", "scorer"), ("player_assists", "assists")):
            pm = grp[grp.market == mkt]
            if mkt == "player_assists":
                pm = pm[pm.outcome == "Over"]  # over 0.5 assists = "gets an assist"
            else:
                pm = pm[pm.outcome != "No"]
            for player, pg in pm.groupby(pm.player.where(pm.player != "", pm.outcome)):
                entry[slot][player] = float((1 / pg.price).median())

        out[frozenset((home, away))] = entry
    return out


def get_market() -> pd.DataFrame | None:
    """Best available market consensus: live fetch > last snapshot > manual CSV."""
    snap = fetch_snapshot()
    if snap is not None and len(snap):
        return consensus(snap)
    if HISTORY.exists():
        hist = pd.read_csv(HISTORY)
        return consensus(hist[hist.fetched_at == hist.fetched_at.max()])
    if MANUAL.exists():
        manual = pd.read_csv(MANUAL, comment="#").dropna()
        if len(manual):
            return consensus(manual)
    return None


if __name__ == "__main__":
    if not os.environ.get("ODDS_API_KEY"):
        print("ODDS_API_KEY not set - no live fetch. Get a free key at https://the-odds-api.com")
        if not MANUAL.exists():
            MANUAL.write_text(MANUAL_TEMPLATE)
            print(f"Wrote template {MANUAL} - fill it with current odds from any odds site.")
    market = get_market()
    if market is None:
        print("No market data available yet.")
    else:
        print(market.round(3).to_string(index=False))
        for match, note in steam_notes().items():
            print(f"steam {match[0]} v {match[1]}: {note}")
