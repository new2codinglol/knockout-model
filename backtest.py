"""Backtest on World Cup 2018, 2022 and the 2026 matches played so far.
Models are refit on data strictly before each tournament (no leakage);
Elo columns are already point-in-time. Prints Brier, log loss, calibration.
"""
import numpy as np
import pandas as pd

from model import HOME_ADV, elo_expectancy, fit_poisson, load_matches, match_probs, training_frame

TOURNAMENTS = [("WC 2018", 2018, "2018-06-01"), ("WC 2022", 2022, "2022-11-01"),
               ("WC 2026 so far", 2026, "2026-06-01")]


def predict_frame(wc: pd.DataFrame, params) -> pd.DataFrame:
    rows = []
    for m in wc.itertuples(index=False):
        p = match_probs(m.home_elo, m.away_elo, params, neutral=m.neutral)
        we = elo_expectancy(m.home_elo + (0 if m.neutral else HOME_ADV) - m.away_elo)
        outcome = int(np.sign(m.home_score - m.away_score)) + 1  # 0 loss 1 draw 2 win
        rows.append({"date": m.date, "match": f"{m.home_team} v {m.away_team}",
                     "p_loss": p["loss"], "p_draw": p["draw"], "p_win": p["win"],
                     "elo_we": we, "outcome": outcome})
    return pd.DataFrame(rows)


def scores(df: pd.DataFrame):
    probs = df[["p_loss", "p_draw", "p_win"]].to_numpy()
    onehot = np.eye(3)[df.outcome]
    brier = ((probs - onehot) ** 2).sum(axis=1).mean()
    logloss = -np.log(np.clip(probs[np.arange(len(df)), df.outcome], 1e-9, 1)).mean()
    uniform_brier = ((np.full(3, 1 / 3) - np.eye(3)) ** 2).sum(axis=1).mean()
    # two-way (home win vs not): model p_win against raw Elo expectancy
    win = (df.outcome == 2).astype(float)
    return {"brier3": brier, "logloss3": logloss, "uniform_brier3": uniform_brier,
            "brier2_model": ((df.p_win - win) ** 2).mean(),
            "brier2_elo": ((df.elo_we - win) ** 2).mean()}


def main():
    matches = load_matches()
    all_preds = []
    print(f"{'tournament':<16} {'n':>3} {'Brier3':>7} {'(unif)':>7} {'LogLoss3':>8} {'Brier2':>7} {'EloBrier2':>9}")
    for name, year, cutoff in TOURNAMENTS:
        params = fit_poisson(training_frame(matches, cutoff=cutoff))
        wc = matches.dropna(subset=["home_score"])
        wc = wc[(wc.tournament == "FIFA World Cup") & (wc.date.dt.year == year)]
        preds = predict_frame(wc, params)
        s = scores(preds)
        print(f"{name:<16} {len(preds):>3} {s['brier3']:>7.4f} {s['uniform_brier3']:>7.4f} "
              f"{s['logloss3']:>8.4f} {s['brier2_model']:>7.4f} {s['brier2_elo']:>9.4f}")
        all_preds.append(preds)

    df = pd.concat(all_preds, ignore_index=True)
    print("\nCalibration (all outcome probs pooled, 3 outcomes per match):")
    long = pd.DataFrame({
        "p": np.concatenate([df.p_loss, df.p_draw, df.p_win]),
        "hit": np.concatenate([(df.outcome == 0), (df.outcome == 1), (df.outcome == 2)]).astype(float),
    })
    long["bucket"] = (long.p * 10).astype(int).clip(0, 9)
    cal = long.groupby("bucket").agg(n=("hit", "size"), predicted=("p", "mean"), realized=("hit", "mean"))
    print(cal.round(3).to_string())


if __name__ == "__main__":
    main()
