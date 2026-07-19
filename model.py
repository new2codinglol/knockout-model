"""Match probability model: Poisson goal GLM on Elo difference (primary),
ordered logit W/D/L (cross-check). Fit on competitive internationals since 2005.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import poisson
from statsmodels.miscmodels.ordinal_model import OrderedModel

DATA = Path(__file__).parent / "data"
HOME_ADV = 100
MAX_GOALS = 10


def load_matches() -> pd.DataFrame:
    return pd.read_csv(DATA / "elo_matches.csv", parse_dates=["date"])


def training_frame(matches: pd.DataFrame, cutoff=None) -> pd.DataFrame:
    df = matches.dropna(subset=["home_score"])
    df = df[(df.tournament != "Friendly") & (df.date >= "2005-01-01")]
    if cutoff is not None:
        df = df[df.date < cutoff]
    return df


def fit_poisson(df: pd.DataFrame):
    """Fit goals ~ elo_diff (per 100 pts, home advantage folded in). Returns (const, coef)."""
    adv = np.where(df.neutral, 0, HOME_ADV)
    home = pd.DataFrame({"goals": df.home_score, "dr": (df.home_elo + adv - df.away_elo) / 100})
    away = pd.DataFrame({"goals": df.away_score, "dr": -home.dr})
    long = pd.concat([home, away], ignore_index=True)
    res = sm.GLM(long.goals, sm.add_constant(long.dr), family=sm.families.Poisson()).fit()
    return res.params["const"], res.params["dr"]


def fit_ordered(df: pd.DataFrame):
    """Ordered logit on match outcome (0 loss / 1 draw / 2 win, home view) ~ elo diff."""
    adv = np.where(df.neutral, 0, HOME_ADV)
    dr = (df.home_elo + adv - df.away_elo) / 100
    outcome = np.sign(df.home_score - df.away_score).astype(int) + 1
    res = OrderedModel(outcome.values, dr.values[:, None], distr="logit").fit(disp=False)
    return res


def elo_expectancy(dr: float) -> float:
    return 1 / (10 ** (-dr / 400) + 1)


def match_probs(elo_a, elo_b, params, neutral=True, knockout=False, offsets=None):
    """P(A win), P(draw), P(B win) in 90'; if knockout, also P(A advances).

    offsets: optional ({atk, def}, {atk, def}) pair from fit_offsets — scales
    the Poisson lambdas so a team's attack/defence split vs Elo expectation
    (which one number can't carry) feeds the scoreline distribution.
    """
    const, coef = params
    dr = elo_a + (0 if neutral else HOME_ADV) - elo_b
    lam_a = np.exp(const + coef * dr / 100)
    lam_b = np.exp(const - coef * dr / 100)
    if offsets is not None:
        oa, ob = offsets
        lam_a *= oa["atk"] * ob["def"]
        lam_b *= ob["atk"] * oa["def"]
    goals = np.arange(MAX_GOALS + 1)
    grid = np.outer(poisson.pmf(goals, lam_a), poisson.pmf(goals, lam_b))
    grid /= grid.sum()  # renormalize the truncated tail
    p_win = np.tril(grid, -1).sum()
    p_draw = np.trace(grid)
    p_loss = np.triu(grid, 1).sum()
    out = {"win": p_win, "draw": p_draw, "loss": p_loss,
           "lam_a": lam_a, "lam_b": lam_b}
    if knockout:
        # ponytail: pens = coin flip nudged 1/3 of the way toward Elo expectancy
        pens = 0.5 + (elo_expectancy(dr) - 0.5) / 3
        out["advance"] = p_win + p_draw * pens
    return out


def derived_markets(lam_a, lam_b):
    """BTTS, over/unders and top scorelines straight from the Poisson grid."""
    goals = np.arange(MAX_GOALS + 1)
    grid = np.outer(poisson.pmf(goals, lam_a), poisson.pmf(goals, lam_b))
    grid /= grid.sum()
    btts = 1 - grid[0, :].sum() - grid[:, 0].sum() + grid[0, 0]
    tot = np.add.outer(goals, goals)
    totals = {line: {"over": float(grid[tot > line].sum()),
                     "under": float(grid[tot < line].sum())}
              for line in (1.5, 2.5, 3.5)}
    idx = np.dstack(np.unravel_index(np.argsort(grid, axis=None)[::-1][:5], grid.shape))[0]
    return {"btts": float(btts), "totals": totals,
            "scorelines": [(f"{i}-{j}", float(grid[i, j])) for i, j in idx]}


def fit_offsets(matches, params, m=8.0):
    """Multiplicative attack/defence offsets vs Elo expectation, per WC2026 team.

    For every 2026 WC game, compare each team's actual goals for/against with
    the Elo model's expected lambdas (pre-match Elos from elo_matches.csv), and
    shrink the ratio toward 1.0 with m pseudo-goals.
    ponytail: m=8 (~6 games of prior) hand-set, not fitted — 6-7 real games is
    all that exists; refit m when a full tournament of history is available.
    """
    wc = matches.dropna(subset=["home_score"])
    wc = wc[(wc.tournament == "FIFA World Cup") & (wc.date.dt.year == 2026)]
    exp_f, exp_a, act_f, act_a = {}, {}, {}, {}
    for r in wc.itertuples():
        p = match_probs(r.home_elo, r.away_elo, params, neutral=r.neutral)
        for team, lf, la, gf, ga in (
                (r.home_team, p["lam_a"], p["lam_b"], r.home_score, r.away_score),
                (r.away_team, p["lam_b"], p["lam_a"], r.away_score, r.home_score)):
            exp_f[team] = exp_f.get(team, 0.0) + lf
            exp_a[team] = exp_a.get(team, 0.0) + la
            act_f[team] = act_f.get(team, 0.0) + gf
            act_a[team] = act_a.get(team, 0.0) + ga
    return {t: {"atk": (act_f[t] + m) / (exp_f[t] + m),
                "def": (act_a[t] + m) / (exp_a[t] + m)} for t in exp_f}


def ordered_probs(elo_a, elo_b, res, neutral=True):
    dr = (elo_a + (0 if neutral else HOME_ADV) - elo_b) / 100
    p = res.predict(np.array([[dr]]))[0]  # [loss, draw, win]
    return {"win": p[2], "draw": p[1], "loss": p[0]}


if __name__ == "__main__":
    df = training_frame(load_matches())
    params = fit_poisson(df)
    print(f"Poisson fit on {len(df)} matches: const={params[0]:.4f} coef={params[1]:.4f}/100 Elo")
    p = match_probs(2171, 2255, params, knockout=True)  # England v Argentina
    print(f"ENG v ARG 90': W {p['win']:.3f} D {p['draw']:.3f} L {p['loss']:.3f}  "
          f"advance {p['advance']:.3f}  (goals {p['lam_a']:.2f} v {p['lam_b']:.2f})")
    op = ordered_probs(2171, 2255, fit_ordered(df))
    print(f"ordered-logit cross-check: W {op['win']:.3f} D {op['draw']:.3f} L {op['loss']:.3f}")
