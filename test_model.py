"""Smoke test: python test_model.py"""
from model import (derived_markets, fit_offsets, fit_poisson, load_matches,
                   match_probs, training_frame)


def main():
    matches = load_matches()
    params = fit_poisson(training_frame(matches))
    p = match_probs(2000, 1800, params, knockout=True)
    q = match_probs(1800, 2000, params, knockout=True)
    assert abs(p["win"] + p["draw"] + p["loss"] - 1) < 1e-6, "probs must sum to 1"
    assert p["win"] > p["loss"], "higher Elo must be favored"
    assert abs(p["win"] - q["loss"]) < 1e-9, "neutral-ground symmetry"
    assert abs(p["advance"] + q["advance"] - 1) < 1e-9, "advance probs sum to 1"
    home = match_probs(2000, 2000, params, neutral=False)
    assert home["win"] > home["loss"], "home advantage must help"

    # derived markets: grid identities
    d = derived_markets(p["lam_a"], p["lam_b"])
    assert 0 < d["btts"] < 1, "btts in (0,1)"
    for line, ou in d["totals"].items():
        assert abs(ou["over"] + ou["under"] - 1) < 1e-6, f"over+under sum to 1 at {line}"
    assert (d["totals"][1.5]["over"] > d["totals"][2.5]["over"] > d["totals"][3.5]["over"]), \
        "P(over) must fall as the line rises"
    assert abs(sum(pr for _, pr in d["scorelines"]) - 1) < 1, "scoreline probs sane"

    # offsets: sane band, and more shrinkage -> closer to 1
    offs = fit_offsets(matches, params)
    for t, o in offs.items():
        assert 0.5 < o["atk"] < 2.0 and 0.5 < o["def"] < 2.0, f"offset out of band: {t} {o}"
    heavy = fit_offsets(matches, params, m=1000.0)
    assert all(abs(o["atk"] - 1) < 0.05 and abs(o["def"] - 1) < 0.05
               for o in heavy.values()), "heavy shrinkage must pull offsets to 1"

    # offsets change lambdas in the right direction (better defence -> fewer conceded)
    strong_def = ({"atk": 1.0, "def": 1.0}, {"atk": 1.0, "def": 0.7})
    padj = match_probs(2000, 1800, params, offsets=strong_def)
    assert padj["lam_a"] < p["lam_a"], "opponent defence offset must cut lambda"
    print("smoke test ok")


if __name__ == "__main__":
    main()
