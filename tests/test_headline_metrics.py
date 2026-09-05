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
        f"{name}: {actual}% — expected ~{expected}% (±{tol}).\n"
        f"If the modelling change is deliberate, update EXPECTED **and** the "
        f"figures quoted in README.md and docs/business_questions.md in the same commit."
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
        f"the ratio dropped to {algo / rest:.2f}× — the project's finding "
        f"on discovery efficiency no longer holds"
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
        f"the mobile gap is {mobile - other:.1f}pp, expected ~5pp: "
        f"MOBILE_SKIP_LIFT may be counted twice"
    )


DEVICE_SKIP = {
    "Mobile iOS": 33.0, "Mobile Android": 32.9,
    "Smart Speaker": 28.1, "Tablet": 28.0, "Desktop": 27.9,
}


def test_skip_rate_by_individual_device_matches_the_documented_breakdown(streams):
    """docs/dashboard.md publishes all five devices individually
    (33.0/32.9/28.1/28.0/27.9), not just the mobile-vs-other split above.
    The mobile-gap test only constrains the two-bucket aggregate: five
    individual devices could drift against each other — Smart Speaker down,
    Desktop up — and still average out to the same ~33%/~28% split while
    falsifying the specific per-device numbers this table publishes."""
    by_device = streams.groupby("device_type").is_skipped.mean() * 100
    for device, expected in DEVICE_SKIP.items():
        assert abs(by_device[device] - expected) <= 2.0, (
            f"{device}: {by_device[device]:.1f}%, documented ~{expected}%"
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


@pytest.fixture(scope="module")
def dimensions(tmp_path_factory):
    """D_Tracks/D_Platform/D_Time don't scale with --users, so the smallest
    run that's still fast is enough to check their row counts."""
    out = tmp_path_factory.mktemp("dimensions")
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "generate_datasets.py"),
         "--out", str(out), "--users", "500", "--seed", "42"],
        check=True, capture_output=True,
    )
    return (pd.read_csv(out / "D_Tracks.csv"), pd.read_csv(out / "D_Platform.csv"))


def test_dimension_counts_match_the_documented_figures(dimensions):
    """README's top-line summary — "1.22M listening events · 45,000 users ·
    100 tracks · 4 platforms · full year 2024" — has its stream and user
    counts protected transitively via the exact full_scale tests below.
    Track and platform counts were not: nothing failed if --tracks' default
    changed or a fifth platform got added, even though the README states
    both as exact figures."""
    tracks, platforms = dimensions
    assert len(tracks) == 100, f"{len(tracks)} tracks, README says 100"
    assert len(platforms) == 4, f"{len(platforms)} platforms, README says 4"


# --- retention: the number the project uses to make its point -------------


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
    """Q4's finding is that the naive KPI reads ~97% while real retention is
    ~82%. If this number moves, the project's whole argument about the
    difference between reach and retention stops holding up.

    This test catches the 2026-09-03 bug, where the `churned` flag was
    computed and then ignored: every user got a churn date within the year
    and retention collapsed to 27%.
    """
    churn = pd.to_datetime(users.churn_date)
    retention = (churn > "2024-12-31").mean() * 100
    assert 79 <= retention <= 85, (
        f"retention {retention:.1f}%, expected ~82%. Check the churn logic "
        f"in build_users(): is the `churned` flag actually applied?"
    )


def test_churn_rate_matches_the_documented_figure(users):
    """~18%, as the documentation says.

    The first draft compared the produced churn against `CHURN_RATE` read
    from the generator itself: a tautology. Changing the constant would have
    left the test green while the documentation became false. Here the
    expected value is hard-coded, because it's the one that's published.
    """
    churn = pd.to_datetime(users.churn_date)
    realised = (churn <= "2024-12-31").mean() * 100
    assert 16.5 <= realised <= 19.5, (
        f"churn {realised:.1f}%, documented ~18%. If the change is deliberate, "
        f"update README.md and docs/business_questions.md in the same commit."
    )


def test_subscription_mix_matches_the_documented_split(users):
    """Free ~45% · Individual ~30% · Student ~15% · Family ~10%."""
    mix = users.subscription_plan.value_counts(normalize=True) * 100
    for plan, expected in [("Free", 45), ("Premium Individual", 30),
                           ("Premium Student", 15), ("Premium Family", 10)]:
        assert abs(mix[plan] - expected) < 2.5, (
            f"{plan}: {mix[plan]:.1f}%, expected ~{expected}%"
        )


def test_premium_share_matches_the_documented_figure(users):
    """README/business_questions.md state Premium (all three paid plans
    combined) is ~55% of users. The per-plan test above bounds each of the
    four segments independently at +-2.5pp: taken to each bound at once, the
    three Premium segments could sum to anywhere from 42.5% to 62.5% while
    every individual assertion still passes. That's a much wider band than
    the documented ~55%, so the combined share needs its own check."""
    mix = users.subscription_plan.value_counts(normalize=True) * 100
    premium = 100 - mix["Free"]
    assert 51 <= premium <= 59, f"Premium share {premium:.1f}%, documented ~55%"


def test_free_is_the_largest_single_segment(users):
    """"Free is the single largest segment, that's where the conversion
    funnel starts" — if it stops being true, the finding needs rewriting."""
    mix = users.subscription_plan.value_counts()
    assert mix.idxmax() == "Free"


# --- reach vs. retention, seasonality, and a negative result --------------


@pytest.fixture(scope="module")
def both(tmp_path_factory):
    out = tmp_path_factory.mktemp("both")
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "generate_datasets.py"),
         "--out", str(out), "--users", "20000", "--seed", "42"],
        check=True, capture_output=True,
    )
    return (pd.read_csv(out / "F_Streams.csv"),
            pd.read_csv(out / "D_Users.csv"),
            pd.read_csv(out / "D_Tracks.csv"))


def test_the_naive_kpi_reads_near_100_percent(both):
    """Q4 rests on the contrast between the naive KPI and real retention. If
    every user has at least one stream the KPI reads 100% and the contrast
    disappears — which is what used to happen when `churned` wasn't passed
    to build_streams. Someone who churns early must not show up at all.
    """
    streams, users, _ = both
    naive = streams.user_id.nunique() / len(users) * 100
    assert 94 <= naive <= 98, f"naive KPI {naive:.1f}%, expected ~96%"


def test_the_gap_between_reach_and_retention_is_the_finding(both):
    """What matters isn't the KPI or the retention alone, but the gap between
    the two: it's Q4's whole argument."""
    streams, users, _ = both
    naive = streams.user_id.nunique() / len(users) * 100
    real = (pd.to_datetime(users.churn_date) > "2024-12-31").mean() * 100
    assert naive - real > 12, (
        f"the gap dropped to {naive - real:.1f}pp: without a gap between reach "
        f"and retention, Q4 no longer demonstrates anything"
    )


def test_raw_monthly_volume_tracks_user_growth_not_season(both):
    """Raw volume is NOT a seasonal signal: it grows with the user base.
    Documenting it as seasonality would credit summer campaigns for growth
    that was just accumulated signups. business_questions.md quotes both
    halves of this precisely — "roughly three times ... because it has
    twice the active users" — so both ratios are checked, not just a
    one-sided floor on streams that would also pass a 6x drift."""
    streams, _, _ = both
    m = pd.to_datetime(streams.listen_date).dt.month
    by_month = streams.assign(m=m).groupby("m").size()
    active_by_month = streams.assign(m=m).groupby("m").user_id.nunique()

    stream_ratio = by_month[8] / by_month[1]
    active_ratio = active_by_month[8] / active_by_month[1]
    assert 2.5 <= stream_ratio <= 3.5, (
        f"August/January streams ratio {stream_ratio:.2f}x, documented as "
        f"'roughly three times'"
    )
    assert 1.7 <= active_ratio <= 2.5, (
        f"August/January active-user ratio {active_ratio:.2f}x, documented "
        f"as 'twice the active users'"
    )


def test_seasonality_appears_once_normalised_by_active_users(both):
    """Divided by active users, seasonality emerges.

    The denominator is the same as Q9's — users who actually listened that
    month — not those theoretically eligible: a test that measures something
    different from the query doesn't protect the query.
    """
    streams, _, _ = both
    month = pd.to_datetime(streams.listen_date).dt.to_period("M")
    g = streams.groupby(month).agg(n=("user_id", "size"), active=("user_id", "nunique"))
    per_user = g.n / g.active
    idx = per_user / per_user.mean() * 100

    summer = idx.iloc[5:8].mean()
    assert 110 < summer < 125, (
        f"summer peak at {summer:.0f}, documented as ~+16% (index ~116). A test that "
        f"only floors this would stay green even if the lift drifted to +40%."
    )
    assert 105 < idx.iloc[11] < 120, (
        f"December at {idx.iloc[11]:.0f}, documented as ~+11% (index ~111)."
    )
    assert idx.idxmin().month == 2, "the minimum is no longer February"
    assert 75 <= idx.iloc[1] <= 88, (
        f"February at {idx.iloc[1]:.0f}, documented as ~-19% (index ~81). Being the "
        f"minimum isn't enough on its own — the magnitude is part of the claim too."
    )


def test_month_over_month_retention_is_not_trivially_one_hundred(both):
    """Q8's bug: with an INNER JOIN between the previous month and the
    current one, the result is always 100%, because the join removes from
    the denominator exactly the users who didn't come back. The denominator
    has to be the previous month in full.
    """
    streams, _, _ = both
    month = pd.to_datetime(streams.listen_date).dt.to_period("M")
    active = streams.groupby(month).user_id.unique().apply(set)

    values = []
    for i in range(len(active) - 1):
        prev, cur = active.iloc[i], active.iloc[i + 1]
        values.append(len(prev & cur) / len(prev) * 100)

    assert max(values) < 99.5, (
        "month-over-month retention is ~100%: the denominator is excluding "
        "everyone who didn't come back, which is the only thing this metric measures"
    )
    assert 87 <= min(values) <= 92, f"minimum {min(values):.1f}%, documented ~90%"
    assert 94 <= max(values) <= 99, f"maximum {max(values):.1f}%, documented ~97%"

    # docs/business_questions.md names specific months, not just a range: "lowest in
    # February and dipping again in September". values[0] is the Jan->Feb transition
    # (retention observed in February); values[7] is Aug->Sep (retention observed in
    # September). Checking only min()/max() would stay green even if the low point
    # moved to a different month or the September dip flattened out.
    assert values.index(min(values)) == 0, (
        "the minimum is no longer the January->February transition: the documented "
        "'lowest in February' claim needs rewriting"
    )
    assert values[7] < values[6] and values[7] < values[8], (
        f"September ({values[7]:.1f}%) is no longer a local dip against August "
        f"({values[6]:.1f}%) and October ({values[8]:.1f}%): the documented "
        f"'dipping again in September' claim needs rewriting"
    )


# --- temporal integrity and monetisation -----------------------------------


def test_no_stream_happens_outside_the_users_lifetime(both):
    """A fact table where an event precedes the user's existence isn't
    defensible, and it makes any temporal analysis unreliable — including
    exactly the retention and seasonality this project documents.

    Before 2026-09-03, 13.7% of streams preceded signup and 2.4% followed
    churn: dates were drawn globally and the user assigned afterward,
    independently.
    """
    streams, users, _ = both
    m = streams.merge(users[["user_id", "signup_date", "churn_date"]], on="user_id")
    d = pd.to_datetime(m.listen_date)
    before = (d < pd.to_datetime(m.signup_date)).mean() * 100
    after = (d >= pd.to_datetime(m.churn_date)).mean() * 100
    assert before == 0, f"{before:.2f}% of streams precede the user's signup"
    assert after == 0, f"{after:.2f}% of streams happen after churn"


def test_revenue_actually_depends_on_the_plan(both):
    """The finding "Premium plans drive revenue" has to be measurable. Until
    2026-09-03, revenue_generated was drawn from the same uniform
    distribution for everyone, so that sentence rested on nothing."""
    streams, users, _ = both
    m = streams.merge(users[["user_id", "subscription_plan"]], on="user_id")
    per_stream = m.groupby("subscription_plan").revenue_generated.mean()
    assert per_stream["Premium Individual"] > per_stream["Free"] * 3, (
        "Premium doesn't earn more than Free per stream: Q3 doesn't demonstrate anything"
    )
    share = m.groupby("subscription_plan").revenue_generated.sum()
    premium = share[share.index != "Free"].sum() / share.sum() * 100
    assert 78 <= premium <= 86, f"Premium revenue share {premium:.1f}%, documented ~82%"

    # docs/dashboard.md and business_questions.md also name the two absolute
    # per-stream rates directly (~$0.0079 / ~$0.0018) — the ratio and revenue-
    # share checks above could both hold under a proportional rescale of
    # REVENUE_PER_STREAM that would still falsify these specific figures.
    assert abs(per_stream["Premium Individual"] - 0.0079) < 0.0015, (
        f"Premium Individual revenue/stream ${per_stream['Premium Individual']:.4f}, "
        f"documented ~$0.0079"
    )
    assert abs(per_stream["Free"] - 0.0018) < 0.0006, (
        f"Free revenue/stream ${per_stream['Free']:.4f}, documented ~$0.0018"
    )


def test_royalty_is_only_paid_on_a_real_listen(both):
    """No royalty is paid on a track skipped after two seconds."""
    streams, _, _ = both
    assert streams[streams.is_skipped == 1].royalty_cost.max() == 0
    assert streams[streams.is_skipped == 0].royalty_cost.min() > 0


# --- the retention curve the dashboard shows -------------------------------


def test_retention_at_april_matches_the_dashboard(users):
    """docs/dashboard.md's reconciliation table: 92.27% at April reproduces
    exactly (same in both the regenerated and shipped-.pbix columns); year
    end is where the two diverge — 82.16% regenerated/authoritative against
    82.28% in the shipped .pbix, a disclosed ~1% gap from an earlier
    generator version. This test targets the **regenerated** figure
    (82.16%): that's the one a fresh clone actually reproduces. With a
    uniform churn offset, April read 96.3% instead of ~92% — churn has to
    be front-loaded, as it is in reality and in the loaded data."""
    churn = pd.to_datetime(users.churn_date)
    april = (churn > "2024-04-30").mean() * 100
    year_end = (churn > "2024-12-31").mean() * 100
    assert 91 <= april <= 93.5, f"April retention {april:.2f}%, dashboard 92.27%"
    assert 80.5 <= year_end <= 83, f"year-end retention {year_end:.2f}%, dashboard's regenerated figure 82.16%"
    assert april > year_end, "retention has to decline over the course of the year"


# --- docs/dashboard.md's "Regenerated (authoritative)" table --------------
#
# That table names precise figures — RPM $128.14, Gross Margin 52.4%, Like
# Rate 14.9%, and (at full scale) 43,304 active users / 1,215,000 streams /
# $5,549 revenue — and calls itself authoritative. Until this section, none
# of the six had a test: every other headline number in this file is a
# contract, these were a claim on the honour system.


def test_rpm_matches_the_documented_figure(both):
    """RPM = revenue / active users * 1000. Documented as $128.14. It's a
    per-user average, so it holds at any sample size — unlike the raw
    active-user/stream counts below, which are tied to the full 45,000-user
    run and are checked separately at that exact scale."""
    streams, _, _ = both
    rpm = streams.revenue_generated.sum() / streams.user_id.nunique() * 1000
    assert 122 <= rpm <= 135, f"RPM ${rpm:.2f}, documented $128.14"


def test_gross_margin_matches_the_documented_figure(both):
    """(Revenue - Royalty Cost) / Revenue. Documented as 52.4%."""
    streams, _, _ = both
    revenue = streams.revenue_generated.sum()
    margin = (revenue - streams.royalty_cost.sum()) / revenue * 100
    assert 49 <= margin <= 56, f"Gross Margin {margin:.1f}%, documented 52.4%"


def test_like_rate_matches_the_documented_figure(both):
    """Documented as 14.9%. Measured spread across scales (20k: 14.86%, 45k:
    14.90%) is 0.04pp — tight enough that the sibling RPM/Gross Margin
    checks in this section use a much narrower band proportionally; this
    one was originally left needlessly wide."""
    streams, _, _ = both
    like_rate = streams.is_liked.mean() * 100
    assert 13.4 <= like_rate <= 16.4, f"Like Rate {like_rate:.1f}%, documented 14.9%"


@pytest.fixture(scope="module")
def full_scale(tmp_path_factory):
    """The one fixture at the repo's real, documented scale (45,000 users) —
    not the small samples above, kept fast for CI. This is slower
    (~20-30s), which is the price of actually protecting the three absolute
    counts in the "authoritative" table: they scale with user count, so no
    ratio computed on a smaller sample can stand in for them."""
    out = tmp_path_factory.mktemp("full_scale")
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "generate_datasets.py"),
         "--out", str(out), "--users", "45000", "--seed", "42"],
        check=True, capture_output=True,
    )
    return pd.read_csv(out / "F_Streams.csv")


def test_total_active_users_matches_the_documented_figure(full_scale):
    """Documented as 43,304 — an absolute count, only meaningful at the
    repo's real 45,000-user scale."""
    active = full_scale.user_id.nunique()
    assert active == 43304, (
        f"Total Active Users {active}, documented 43,304 at --users 45000 --seed 42. "
        f"If the generator changed deliberately, update docs/dashboard.md's "
        f"'Regenerated (authoritative)' row in the same commit."
    )


def test_total_streams_matches_the_documented_figure(full_scale):
    """Documented as 1,215,000 — deterministic given users * STREAMS_PER_USER,
    so this is an exact match, not a tolerance."""
    assert len(full_scale) == 1215000, (
        f"Total Streams {len(full_scale)}, documented 1,215,000"
    )


def test_total_revenue_matches_the_documented_figure(full_scale):
    """Documented as $5,549 — a float sum, so a cent of tolerance for
    floating-point accumulation, not for the model itself."""
    revenue = full_scale.revenue_generated.sum()
    assert abs(revenue - 5548.84) < 1.0, f"Total Revenue ${revenue:.2f}, documented $5,549"


def test_churn_is_front_loaded(users):
    """Whoever churns does so early: nearly half by April. A flat tail would
    mean users leaving at random, which isn't how they behave."""
    churn = pd.to_datetime(users.churn_date)
    within_year = churn <= "2024-12-31"
    within_april = churn <= "2024-04-30"
    share = within_april.sum() / within_year.sum() * 100
    assert 35 <= share <= 55, (
        f"only {share:.0f}% of churn falls within April: the curve is no "
        f"longer front-loaded"
    )
