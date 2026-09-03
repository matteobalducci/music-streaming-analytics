"""The numbers in the README have to survive a change to the generator.

WHY THIS EXISTS
---------------
The README, the dashboard and the project write-up all quote specific figures:
algorithmic recommendations skip at ~42% against ~22% for editorial and search,
mobile skips ~33% against ~28% elsewhere. Those are the findings, not decoration.

At some point `SKIP_BY_SOURCE` was changed from the *base* probabilities to the
*realised* ones, which double-counted `MOBILE_SKIP_LIFT` and quietly pushed every
rate two points up — 44%/24%/24%. Nothing failed. The dataset still generated,
the quality checks still passed, the SQL still ran. Only the claims stopped being
true, and a reader running the repo would have got numbers that contradicted the
document describing it.

These tests turn the headline figures into a contract. If a modelling change is
deliberate, one of them fails and the README gets updated in the same commit. If
it was an accident, it gets caught before it ships.

They run on a small deterministic sample, so CI stays fast.
"""

import os
import subprocess
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The figures quoted in README.md and docs/business_questions.md, measured
# against the dataset loaded into BigQuery. Tolerances are wide enough for
# sampling noise on a small run, tight enough that a 2pp modelling drift fails.
EXPECTED = {
    "skip_algorithmic": (42.0, 1.5),
    "skip_editorial": (22.0, 1.5),
    "skip_search": (22.0, 1.5),
    "skip_mobile": (33.0, 1.5),
    "skip_other_devices": (28.0, 1.5),
    "skip_overall": (30.0, 1.5),
}


@pytest.fixture(scope="module")
def streams(tmp_path_factory):
    """Generate a deterministic sample and read the fact table."""
    out = tmp_path_factory.mktemp("data")
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "generate_datasets.py"),
         "--out", str(out), "--users", "8000", "--seed", "42"],
        check=True, capture_output=True,
    )
    return pd.read_csv(out / "F_Streams.csv")


def pct(series) -> float:
    return round(series.mean() * 100, 1)


def check(name, actual):
    expected, tol = EXPECTED[name]
    assert abs(actual - expected) <= tol, (
        f"{name}: {actual}% — atteso ~{expected}% (±{tol}).\n"
        f"Se la modifica al modello è voluta, aggiorna EXPECTED **e** i numeri "
        f"citati in README.md e docs/business_questions.md nello stesso commit."
    )


# --- discovery efficiency: the headline finding of the whole project ------


def test_algorithmic_skip_rate(streams):
    check("skip_algorithmic", pct(streams[streams.stream_source == "Algorithmic"].is_skipped))


def test_editorial_skip_rate(streams):
    check("skip_editorial", pct(streams[streams.stream_source == "Editorial"].is_skipped))


def test_search_skip_rate(streams):
    check("skip_search", pct(streams[streams.stream_source == "Search"].is_skipped))


def test_algorithmic_skips_roughly_twice_as_much_as_the_rest(streams):
    """The finding is the *ratio*, not the absolute number: if the recommender
    ever stops looking worse than editorial and search, the story changes."""
    algo = streams[streams.stream_source == "Algorithmic"].is_skipped.mean()
    rest = streams[streams.stream_source != "Algorithmic"].is_skipped.mean()
    assert algo / rest > 1.6, (
        f"il rapporto è sceso a {algo / rest:.2f}× — la conclusione del progetto "
        f"sulla discovery efficiency non regge più"
    )


# --- device experience ----------------------------------------------------


MOBILE = ["Mobile iOS", "Mobile Android"]


def test_mobile_skip_rate(streams):
    check("skip_mobile", pct(streams[streams.device_type.isin(MOBILE)].is_skipped))


def test_non_mobile_skip_rate(streams):
    check("skip_other_devices", pct(streams[~streams.device_type.isin(MOBILE)].is_skipped))


def test_the_mobile_gap_is_about_five_points(streams):
    """MOBILE_SKIP_LIFT is 0.05 and the README quotes the gap it produces.
    This is the assertion that would have caught the double-counted lift."""
    mobile = streams[streams.device_type.isin(MOBILE)].is_skipped.mean() * 100
    other = streams[~streams.device_type.isin(MOBILE)].is_skipped.mean() * 100
    assert 3.5 <= mobile - other <= 6.5, (
        f"lo scarto mobile è {mobile - other:.1f}pp, atteso ~5pp: "
        f"MOBILE_SKIP_LIFT potrebbe essere contato due volte"
    )


# --- overall shape --------------------------------------------------------


def test_overall_skip_rate(streams):
    check("skip_overall", pct(streams.is_skipped))


def test_source_mix_is_stable(streams):
    """40/20/40 across Algorithmic / Editorial / Search: the marts assume it."""
    mix = streams.stream_source.value_counts(normalize=True)
    assert abs(mix["Algorithmic"] - 0.40) < 0.02
    assert abs(mix["Editorial"] - 0.20) < 0.02
    assert abs(mix["Search"] - 0.40) < 0.02


def test_skipped_streams_are_short_and_rarely_liked(streams):
    """A skip that lasted four minutes is not a skip: guards the semantics the
    duration and engagement metrics are built on."""
    skipped = streams[streams.is_skipped == 1]
    played = streams[streams.is_skipped == 0]
    assert skipped.listen_duration_sec.max() <= 30
    assert played.listen_duration_sec.min() > 30
    assert skipped.is_liked.mean() < played.is_liked.mean() / 3


# --- retention: il numero che il progetto usa per dimostrare il suo punto ---


@pytest.fixture(scope="module")
def users(tmp_path_factory):
    out = tmp_path_factory.mktemp("users")
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "generate_datasets.py"),
         "--out", str(out), "--users", "8000", "--seed", "42"],
        check=True, capture_output=True,
    )
    return pd.read_csv(out / "D_Users.csv")


def test_retention_matches_the_documented_figure(users):
    """La conclusione della Q4 e' che il KPI ingenuo legge ~97% mentre la
    retention vera e' ~82%. Se questo numero si muove, l'intero argomento del
    progetto sulla differenza fra portata e retention smette di reggere.

    Questo test coglie il bug del 2026-09-03, in cui il flag `churned` veniva
    calcolato e poi ignorato: ogni utente riceveva una data di abbandono entro
    l'anno e la retention crollava al 27%.
    """
    churn = pd.to_datetime(users.churn_date)
    retention = (churn > "2024-12-31").mean() * 100
    assert 79 <= retention <= 85, (
        f"retention {retention:.1f}%, attesa ~82%. Verifica la logica di churn "
        f"in build_users(): il flag `churned` viene davvero applicato?"
    )


def test_churn_rate_tracks_the_configured_constant(users):
    """CHURN_RATE e' 0.18 e la documentazione cita 17,7%: devono coincidere."""
    from importlib import util
    spec = util.spec_from_file_location(
        "gen", os.path.join(ROOT, "scripts", "generate_datasets.py"))
    gen = util.module_from_spec(spec)
    spec.loader.exec_module(gen)

    churn = pd.to_datetime(users.churn_date)
    realised = (churn <= "2024-12-31").mean()
    assert abs(realised - gen.CHURN_RATE) < 0.02, (
        f"abbandoni reali {realised:.1%} contro CHURN_RATE={gen.CHURN_RATE:.0%}: "
        f"la costante non governa piu' i dati che produce"
    )


def test_subscription_mix_matches_the_documented_split(users):
    """Free ~45% · Individual ~30% · Student ~15% · Family ~10%."""
    mix = users.subscription_plan.value_counts(normalize=True) * 100
    for plan, expected in [("Free", 45), ("Premium Individual", 30),
                           ("Premium Student", 15), ("Premium Family", 10)]:
        assert abs(mix[plan] - expected) < 2.5, (
            f"{plan}: {mix[plan]:.1f}%, atteso ~{expected}%"
        )


def test_free_is_the_largest_single_segment(users):
    """«Free e' il segmento singolo piu' grande, da li' parte il funnel di
    conversione» — se smette di esserlo, la conclusione va riscritta."""
    mix = users.subscription_plan.value_counts()
    assert mix.idxmax() == "Free"
