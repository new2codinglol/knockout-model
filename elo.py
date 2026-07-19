"""Compute World Football Elo ratings (eloratings.net formula) from full match history.

Downloads martj42/international_results (the upstream of the Kaggle 1872-2024 dataset,
updated through the current tournament). Writes:
  data/elo_matches.csv  - every match with pre-match Elo for both teams
  data/current_elo.csv  - latest rating per team
"""
from pathlib import Path

import pandas as pd
import requests

DATA = Path(__file__).parent / "data"
RESULTS_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
START_ELO = 1500
HOME_ADV = 100

MAJOR_FINALS = {
    "uefa euro", "copa américa", "african cup of nations", "afc asian cup",
    "gold cup", "concacaf championship", "confederations cup", "oceania nations cup",
}


def k_factor(tournament: str) -> float:
    t = tournament.lower()
    if t == "fifa world cup":
        return 60
    if t in MAJOR_FINALS:
        return 50
    if "qualification" in t or "nations league" in t:
        return 40
    if t == "friendly":
        return 20
    return 30


def load_results() -> pd.DataFrame:
    path = DATA / "results.csv"
    if not path.exists():
        DATA.mkdir(exist_ok=True)
        path.write_bytes(requests.get(RESULTS_URL, timeout=60).content)
    df = pd.read_csv(path, parse_dates=["date"])
    # patch in results the upstream dataset hasn't recorded yet (e.g. last night's semi)
    manual = DATA / "manual_results.csv"
    if manual.exists():
        fix = pd.read_csv(manual, parse_dates=["date"])
        df = df.set_index(["date", "home_team", "away_team"])
        fix = fix.set_index(["date", "home_team", "away_team"])
        df.update(fix)
        missing = fix.index.difference(df.index)
        if len(missing):
            df = pd.concat([df, fix.loc[missing]])
        df = df.reset_index().sort_values("date", kind="stable")
    return df


def compute_elo(df: pd.DataFrame):
    """Return (df with pre-match home_elo/away_elo columns, {team: current rating})."""
    ratings: dict[str, float] = {}
    home_elos, away_elos = [], []
    for row in df.itertuples(index=False):
        eh = ratings.get(row.home_team, START_ELO)
        ea = ratings.get(row.away_team, START_ELO)
        home_elos.append(eh)
        away_elos.append(ea)
        if pd.isna(row.home_score):
            continue  # future fixture
        dr = eh + (0 if row.neutral else HOME_ADV) - ea
        we = 1 / (10 ** (-dr / 400) + 1)
        w = 1.0 if row.home_score > row.away_score else 0.0 if row.home_score < row.away_score else 0.5
        diff = abs(row.home_score - row.away_score)
        g = 1.0 if diff <= 1 else 1.5 if diff == 2 else (11 + diff) / 8
        delta = k_factor(row.tournament) * g * (w - we)
        ratings[row.home_team] = eh + delta
        ratings[row.away_team] = ea - delta
    out = df.copy()
    out["home_elo"] = home_elos
    out["away_elo"] = away_elos
    return out, ratings


def main():
    df = load_results()
    matches, ratings = compute_elo(df)
    matches.to_csv(DATA / "elo_matches.csv", index=False)
    cur = pd.Series(ratings, name="elo").sort_values(ascending=False)
    cur.rename_axis("team").round(1).to_csv(DATA / "current_elo.csv")

    played = matches.dropna(subset=["home_score"])
    wc26 = played[(played.tournament == "FIFA World Cup") & (played.date.dt.year == 2026)]
    assert len(wc26) > 50, "2026 World Cup matches missing from dataset - add data/manual_results.csv"
    print(f"{len(played)} matches through {played.date.max().date()}  ({len(wc26)} WC2026 played)")
    print("\nTop 12 Elo (sanity-check vs eloratings.net):")
    print(cur.head(12).round(0).to_string())


if __name__ == "__main__":
    main()
