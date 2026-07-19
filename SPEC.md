# SPEC — WC2026 knockout model site v2 ("Neon Onyx", graph-first)

Approved 2026-07-16. Replaces the current `site/template.html` + presentation half of
`site/build.py`. The Python model pipeline (`elo.py`, `model.py`, `odds.py`,
`predict.py`) is out of scope — do not touch it.

## What this is

A single static page presenting the WC2026 knockout prediction model, rebuilt around
**four charts**. Same architecture as today: `python site/build.py` reads data files,
renders every number/chart as static markup into `site/template.html` via
`{{TOKEN}}` replacement, writes `site/index.html`. The page must be fully readable
with **no JavaScript** — all charts are inline SVG generated at build time in Python.

Context: the ENG v ARG semifinal is being played as this is built. Data is the
pre-match snapshot; the page is rebuilt after each `predict.py` run, and the bracket
will change tonight. **Render from data, not from hardcoded team names**, wherever
possible (see Resilience).

## Inputs (data contract)

`data/site_data.json` — current shape (see the real file; keep `build.py` consuming it):
- `matches[]`: `{teams: [a, b], date, label, p_pairing, model: {win,draw,loss}, model_advance, market: {win,draw,loss}|null, blend: {...}|null, blend_advance|null, divergence_win|null, steam}`
- `winner_model` / `winner_blend`: `{team: prob}` (blend may be `null`)
- `retro[]`: `{date, match, model_WDL, actual, p_win, p_draw, p_loss, called: "yes"|"no"}`
- `elo_top`: `{team: elo}` (12 teams)
- `goals_2026`: `{team: {games, scored, conceded}}`
- `blend_weight_model`: float

`data/odds_history.csv` — NEW input for the timeline chart:
`fetched_at,commence,home_team,away_team,book,home_odds,draw_odds,away_odds`
(~350 rows, multiple books per snapshot). Per snapshot (`fetched_at`), de-vig each
book (implied prob = 1/odds, normalised to sum 1) and take the median across books
→ consensus implied prob for home/draw/away over time. Chart the match with the most
snapshots (currently England v Argentina).

## Page structure — DASHBOARD (revised 2026-07-16)

The page reads as a **monitoring dashboard**, not an editorial long-scroll: a dense
grid of self-contained panels, most of the content visible within the first couple
of viewports on desktop. Kill the magazine hero headline; panels carry small-caps
mono titles. Minimal prose — one caption line per panel, computed in build.py where
feasible.

1. **Slim top bar** — site title, generated-at timestamp, method chip
   ("Elo + Poisson · blend 30/70 with market").
2. **KPI row** — 4 stat tiles (big mono number + small label, no plots):
   tournament favourite + prob, biggest model−market divergence (pts + outcome),
   calibration hit rate (n called / N), snapshots tracked / books count. Tiles
   render from data; drop a tile gracefully if its input is null.
3. **Panel grid** (12-col, cards spanning 4–8 cols; single column on mobile):
   - Winner probabilities (Chart 1) — widest panel.
   - Featured match: 90-min W/D/L stacked bars (model/market/blend) in one panel;
     divergence (Chart 2) + steam line in an adjacent one.
   - Odds timeline (Chart 3).
   - Remaining fixtures — compact rows in one panel (model W/D/L bar + p_pairing).
   - Calibration (Chart 4) panel; the full retro table lives in a `<details>`
     inside it (it remains the accessibility table view).
   - Elo top-12 and goals-per-game minis as small side panels.
4. **Footer line** — method caveats (blend weight unfitted; model-only where no
   market prices exist), data-source note.

Dashboard styling: tighter spacing than the editorial version, hairline-bordered
cards on the onyx page surface, consistent panel header treatment (small-caps mono,
muted, with the neon accent used sparingly — e.g. a 2px accent tick on panel
headers, not full-color headings). Numbers stay mono/tabular. The four charts
themselves are unchanged in form; resize/re-margin them to their panels.

## The four charts (all inline SVG, built in Python)

Follow these mark specs everywhere: bars thin with 4px rounded data-ends anchored at
the baseline; 2px line strokes; circle markers ≥ 8px hit area; 2px surface-colored gap
between adjacent/stacked fills; recessive grid (hairline, low-contrast) and axes;
**one axis only, never dual**; text (labels, values) always in text tokens, never in
series color; every mark carries a native SVG `<title>` tooltip (works with no JS).
Legend present when ≥ 2 series, plus direct labels on the series themselves (the
palette's blue↔magenta pair sits in the CVD floor band — direct labels are the
mandated secondary encoding, not optional).

1. **Winner probabilities** — horizontal bar chart, teams sorted desc by blend prob.
   Single-hue bars (slot 1 green) showing `winner_blend`, with a contrasting tick/
   diamond marker at `winner_model` (legend: "blend" bar, "model only" marker).
   Direct value labels at bar ends. If `winner_blend` is null, plot `winner_model`
   alone and drop the marker + legend.
2. **Model − market divergence** — diverging horizontal bars, one row per outcome
   (Team A win / draw / Team B win) of the featured match: `model.x − market.x` in
   percentage points around a zero baseline with a neutral midline. Green pole =
   model higher than market, magenta pole = market higher. Axis in ±pts. Only for
   matches with market data.
3. **Odds timeline** — line chart, x = snapshot time, y = implied probability (%),
   three series (home win / draw / away win) wearing the same entity colours as the
   stacked W/D/L bars (team A green, draw neutral grey, team B magenta), direct-labeled
   at line ends. Points at each snapshot with `<title>` (time, book count, prob).
   Include a `<details>` fallback table of the plotted consensus values.
4. **Calibration record** — dot strip/scatter: x = match date (29 retro matches),
   y = model's probability for the outcome that actually happened
   (pick p_win/p_draw/p_loss matching `actual`), dot styled by `called`:
   hit = filled status-green dot, miss = status-red ring (shape + color, never color
   alone). Reference line at 33.3% (coin-flip for 3 outcomes). Headline stat: hits/N
   called. The existing hit/miss cell strip may stay as a compact summary.

## V2 extras (added 2026-07-16)

`site_data.json` now carries `"model_version": "V2"` and, per match, `"model_v1"`
(Elo-only W/D/L for transparency — V2 = Elo + per-team goal offsets) plus an
`"extras"` object:

```
extras: {
  btts:   {model, market|null, blend|null},          # P(both teams score)
  totals: {"1.5"|"2.5"|"3.5": {model_over, market_over|null, blend_over|null}},
  scorelines: [["1-0", p], ...5],                    # most likely correct scores
  players: [{player, team, goals, assists, p_score, p_assist,
             p_score_mkt|null, p_assist_mkt|null}]   # anytime scorer/assist props
}
```

New panels (per match with extras; skip a panel/row gracefully when its data is
null — matches without extras render exactly as before):

- **Goals markets** — per match: BTTS-yes and Over-per-line as paired short
  horizontal bars (model vs market, blend tick), plus the top scorelines as a
  compact labeled list or small bars. Model bar in slot-1 green, market in
  magenta (polarity convention from the divergence chart), text in text tokens.
- **Player props** — per match: top players as rows — name, tournament G/A in
  mono, then a dot-pair or paired bar for model vs market anytime-scorer prob
  (market dot absent when books don't quote the player); assist prob as a mono
  column. Table-like panel is fine (it IS the accessible view); no new chart
  form needed. Caveat line: "market implied probs keep the bookmaker margin;
  shares assume the player starts."
- **V2 chip**: the top-bar method chip becomes "model V2 · Elo+offsets Poisson ·
  blend 30/70 with market". Footer method sentence mentions the offsets layer
  and that V1 (Elo-only) numbers are in the data payload.
- The featured-match panel may show a small "V1 model" secondary row or note
  only if it fits cleanly — optional, builder's judgment.

## Theme — Neon Onyx (committed dark; there is no light mode)

Near-black onyx surfaces with green-tinted OKLCH neutrals and neon accents. Tokens
(define as CSS custom properties):

- Surfaces: page `#0a0b0a`; raised card ≈ `oklch(0.17 0.01 150)`; hairline borders
  ≈ `oklch(0.26 0.012 150)`.
- Text: primary ≈ `oklch(0.93 0.01 150)`; secondary ≈ `oklch(0.72 0.015 150)`;
  muted ≈ `oklch(0.55 0.015 150)`.
- **UI accent** (headings/links/emphasis, not chart series): bright neon green
  `#4ade80`, used with discipline.
- **Chart categorical slots (validated on `#0a0b0a`, fixed order, never cycled):**
  slot 1 `#16a34a` (green), slot 2 `#c026d3` (magenta), slot 3 `#3b82f6` (blue).
- Diverging pair (chart 2): green pole `#16a34a` / magenta pole `#c026d3`, neutral
  gray midline.
- Status (chart 4 + bet/result badges): good `#4ade80`, bad `#f43f5e` — always with
  shape/label, never color alone.
- Neon glow: subtle `filter: drop-shadow(0 0 6px <color at ~35% alpha>)` on chart
  strokes/bar ends and heading accents. Subtle — glow is atmosphere, not signal.
- Type: system font stacks only (no webfonts): a sans stack for prose, a mono stack
  for all numerals/axis labels/tabular data (`font-variant-numeric: tabular-nums`).
- Motion: ambient at most (e.g. a slow glow pulse). Must respect
  `prefers-reduced-motion: reduce` (disable all animation). No JS required for any
  content or chart; tiny inline JS is allowed only as progressive enhancement
  (e.g. a crosshair on the timeline) and the page must be complete without it.

## Resilience (the bracket changes tonight)

`build.py` must not crash when:
- no match has `market != null` (skip featured-match section + charts 2/3 gracefully);
- `winner_blend` is null; fewer/more `matches`; a team absent from `goals_2026`;
- `odds_history.csv` missing or empty (skip chart 3).
Team names come from the data, not literals. The old build.py's ENG/ARG-specific
tokens and prose go away.

## Accessibility

- Every chart: `role="img"` + meaningful `aria-label` on the SVG, `<title>` per mark.
- A table view exists for every dataset shown as a chart (retro table, `<details>`
  tables for winner probs and odds timeline; Elo table already tabular).
- Text contrast ≥ 4.5:1 on surfaces; chart marks ≥ 3:1 (palette pre-validated).

## Deliverables & verification

- New `site/template.html`, updated `site/build.py` (chart rendering may live in
  `site/charts.py` if build.py gets crowded — builder's call).
- `python site/build.py` runs green from the repo root and the leftover-token assert
  passes; open the output in a browser and screenshot it.
- Keep the inlined JSON payload `<script type="application/json">` block.
- `FRONTEND_LOG.md` noting assumptions/deviations.
- Do not touch `predict.py`, `elo.py`, `model.py`, `odds.py`, or anything in `data/`.
