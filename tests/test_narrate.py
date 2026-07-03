"""Unit tests for the rationale templating."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from narrate import build_rationales, qualifier, rationale  # noqa: E402


def _row(**over):
    base = {
        "author_canonical": "Alice",
        "ownership_concentration": 0.95,
        "code_survival_tenure_normalized": 0.60,
        "coupling_criticality": 0.80,
        "review_leverage": 0.40,
        "bus_factor_flag": False,
        "review_data_imputed": False,
    }
    base.update(over)
    return pd.Series(base)


def test_qualifier_bands():
    assert qualifier(0.95) == "top-decile"
    assert qualifier(0.80) == "top-quartile"
    assert qualifier(0.55) == "above-median"
    assert qualifier(0.10) == "below-median"


def test_rationale_leads_with_two_strongest():
    text = rationale(_row())
    assert text.startswith("Top-decile concentrated ownership")
    assert "central to co-change" in text  # second-strongest signal
    assert "review" not in text.lower()    # 0.40 is below the median cutoff
    assert text.endswith(".")


def test_rationale_flags_appended():
    text = rationale(_row(bus_factor_flag=True, review_data_imputed=True))
    assert "bus-factor risk" in text
    assert "no review data (median-imputed)" in text


def test_imputed_review_never_leads():
    # Review percentile is imputed at 0.5; even if it were the only signal
    # >= 0.5 it must not be presented as evidence.
    text = rationale(_row(
        ownership_concentration=0.1, coupling_criticality=0.1,
        code_survival_tenure_normalized=0.1, review_leverage=0.5,
        review_data_imputed=True,
    ))
    assert text.startswith("No signal above the repo median")


def test_build_rationales_vectorized():
    df = pd.DataFrame([_row(), _row(author_canonical="Bob", bus_factor_flag=True)])
    out = build_rationales(df)
    assert len(out) == 2 and all(isinstance(s, str) and s for s in out)
