# The Knockout Model — World Cup 2026

A match-prediction model I ran live through the World Cup 2026 knockout stage,
from the round of 32 to the final. It called **24 of the 32 knockout games
(75%)** by modal outcome, graded prospectively — every prediction was published
to its dashboard before kickoff, then scored against the result.

**Live dashboard:** https://new2codinglol.github.io/knockout-model/

Final verdict of the tournament: the model had Spain as favourites for the
final against the market's coin-flip lean — Spain won it 1-0 in extra time.

## How it works

```
elo.py          rebuild Elo ratings from ~49,500 internationals (1872–present)
predict.py      fit + predict + fetch odds → data/site_data.json
report.py       terminal report (the daily driver)
site/build.py   render the static dashboard (no JS frameworks, inline SVG charts)
test_model.py   smoke tests
backtest.py     out-of-sample check on WC 2018 / 2022 (no leakage: models refit
                on data strictly before each tournament)
```

The model itself, in three layers:

1. **Elo → goals.** A Poisson GLM maps Elo difference to expected goals for
   each side, fit on competitive internationals since 2005. A full scoreline
   grid gives win/draw/loss, totals, BTTS, and correct-score probabilities.
2. **Per-team attack/defence offsets** ("V2"): multiplicative corrections fit
   on the tournament's own games — how each team's goals for/against ran
   versus Elo expectation, shrunk toward 1.0 with pseudo-goals so seven games
   can't shout. This layer is what flipped the final's call to Spain when
   Elo-only leaned Argentina.
3. **Market blend.** De-vigged, Pinnacle-weighted consensus from ~50 books
   (The Odds API), blended 30/70 model/market. The gap between model and
   market — not the model alone — is what flags value.

Player anytime-scorer/assist props are derived from tournament goal shares
(ESPN leaderboard), and priced against the books' player markets.

## Honesty notes

- The 75% track record is the **Elo-only V1 model**, graded prospectively.
  V2's offsets are fit in-sample on the same tournament, so V2 is shown next
  to V1 everywhere but never claims the track record.
- Draws are the model's blind spot (it called none as modal outcome — modal
  calls rarely favour draws), and third-place games broke its totals model:
  it leaned Under 2.5 in a game that finished 6-4.
- The blend weight (0.30) is hand-set, not fitted — there's no historical
  odds corpus in the repo to fit it on. Deliberate shortcuts are marked with
  `ponytail:` comments in the source.

## Run it

```
pip install -r requirements.txt
python elo.py        # ~1 min: rebuilds ratings from the bundled results data
python predict.py    # set ODDS_API_KEY for live odds, else uses bundled snapshots
python report.py
```

Results data is the public [martj42 international results
dataset](https://github.com/martj42/international_results) (bundled in
`data/`); odds via [The Odds API](https://the-odds-api.com) free tier.

Not betting advice. It told me Spain would win the final in 90 minutes;
they needed 106.
