"""Player-level WC2026 stats (ESPN) and simple prop pricing.

Pulls the tournament goal/assist leaderboards from ESPN's public JSON API
(FBref would add shots-on-target but sits behind a Cloudflare challenge),
caches to data/player_stats.csv (re-fetched when older than a day), and
prices anytime-scorer / assist props from tournament shares:

    P(scores)  = 1 - exp(-lam_team * player_goals / team_goals)
    P(assist)  = 1 - exp(-lam_team * player_assists / team_goals)

ponytail: shares assume the player starts and plays ~90 — no minutes model,
no lineup feed. Add a minutes-expectation factor if props become load-bearing.
"""
import math
import re
import time
from pathlib import Path

import pandas as pd
import requests

DATA = Path(__file__).parent / "data"
CACHE = DATA / "player_stats.csv"
CACHE_MAX_AGE_S = 24 * 3600
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/statistics"
_MGA = re.compile(r"M: (\d+), G: (\d+):? A: (\d+)")


def _fetch() -> pd.DataFrame:
    r = requests.get(ESPN, timeout=30)
    r.raise_for_status()
    players = {}
    for cat in r.json()["stats"]:
        for lead in cat.get("leaders", []):
            ath = lead["athlete"]
            m = _MGA.search(lead.get("shortDisplayValue", ""))
            if not m:
                continue
            players[ath["id"]] = {
                "team": ath.get("team", {}).get("displayName", ""),
                "player": ath["displayName"],
                "matches": int(m.group(1)),
                "goals": int(m.group(2)),
                "assists": int(m.group(3)),
            }
    out = pd.DataFrame(players.values())
    if not len(out):
        raise ValueError("ESPN leaderboards empty")
    out.to_csv(CACHE, index=False)
    return out


def load_stats() -> pd.DataFrame | None:
    """Cached ESPN leader stats, re-fetched when stale; None if neither works."""
    fresh = CACHE.exists() and (time.time() - CACHE.stat().st_mtime) < CACHE_MAX_AGE_S
    if not fresh:
        try:
            return _fetch()
        except Exception as e:  # offline -> stale cache beats nothing
            print(f"NOTE: ESPN stats fetch failed ({e}); "
                  f"{'using stale cache' if CACHE.exists() else 'no player stats'}")
    return pd.read_csv(CACHE) if CACHE.exists() else None


def team_props(stats: pd.DataFrame, team: str, lam_team: float,
               team_goals: int, top_n: int = 5) -> list[dict]:
    """Prop prices for a team's top scorers, given its expected goals this match.

    team_goals is the team's actual tournament total (from match data) so
    shares stay exact even though ESPN's leaderboard is top-50 only.
    """
    sq = stats[stats.team == team]
    if not len(sq) or not team_goals:
        return []
    sq = sq.sort_values(["goals", "assists"], ascending=False).head(top_n)
    # ponytail: +0.5 pseudo-goals so a zero-goal creator isn't priced at a
    # literal 0% — replace with shots/xG shares if a source ever opens up
    denom = team_goals + 0.5 * len(sq)
    rows = []
    for r in sq.itertuples():
        rows.append({
            "player": r.player, "team": team,
            "goals": int(r.goals), "assists": int(r.assists),
            "p_score": 1 - math.exp(-lam_team * (r.goals + 0.5) / denom),
            "p_assist": 1 - math.exp(-lam_team * (r.assists + 0.5) / denom),
        })
    return rows


if __name__ == "__main__":
    s = load_stats()
    if s is None:
        print("no player stats available")
    else:
        print(f"{len(s)} leaderboard players cached; Argentina @ lam=1.5, 19 team goals:")
        for p in team_props(s, "Argentina", 1.5, 19):
            print(f"  {p['player']:24s} {p['goals']}g {p['assists']}a  "
                  f"score {p['p_score']:.1%}  assist {p['p_assist']:.1%}")
