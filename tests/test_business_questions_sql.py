"""The queries are executed, and their output is checked against the docs.

WHY THIS EXISTS
---------------
`test_headline_metrics.py` asserts what the *generator* produces. It said nothing
about whether the SQL computes what its comments claim. An audit proved the gap
by swapping Q8's LEFT JOIN for an INNER JOIN — the change that makes
month-over-month retention read 100% — and all 24 tests stayed green.

Running the queries immediately found a second defect the reading tests could not
have caught: Q10 derived the weekend from `EXTRACT(DAYOFWEEK)`, whose day
numbering differs between engines, so the same query meant different things
depending on where it ran. It now reads `dim_time.is_weekend`.

See `conftest.py` for how the BigQuery SQL is transpiled and run on DuckDB, and
for what that does and does not prove.
"""

def one(frame, column):
    return frame[column].iloc[0]


def by(frame, key_col, key, value_col):
    return frame.loc[frame[key_col] == key, value_col].iloc[0]


# --- every query still parses and runs -----------------------------------


def test_all_ten_questions_are_present_and_executable(run_query):
    """A query that no longer parses is a broken claim, not a broken test."""
    expected = {f"Q{n}" for n in range(1, 11)}
    assert expected.issubset(set(run_query.available)), (
        f"missing {sorted(expected - set(run_query.available))}"
    )
    for name in sorted(expected):
        assert not run_query(name).empty, f"{name} returns no rows"


# --- Q1 · discovery efficiency, the headline finding ---------------------


def test_q1_reproduces_the_documented_skip_rates(run_query):
    q1 = run_query("Q1")
    assert abs(by(q1, "stream_source", "Algorithmic", "skip_rate_pct") - 42.0) < 1.5
    assert abs(by(q1, "stream_source", "Editorial", "skip_rate_pct") - 22.0) < 1.5
    assert abs(by(q1, "stream_source", "Search", "skip_rate_pct") - 22.0) < 1.5


def test_q1_keeps_algorithmic_clearly_worst(run_query):
    """The finding is the ratio, not the absolute number."""
    q1 = run_query("Q1").set_index("stream_source")
    algo = q1.loc["Algorithmic", "skip_rate_pct"]
    others = q1.drop("Algorithmic")["skip_rate_pct"].mean()
    assert algo / others > 1.6, f"ratio dropped to {algo / others:.2f}×"


# --- Q2 · device experience ----------------------------------------------


def test_q2_reproduces_the_documented_device_gap(run_query):
    q2 = run_query("Q2").set_index("device_type")["skip_rate_pct"]
    mobile = q2[["Mobile iOS", "Mobile Android"]].mean()
    others = q2.drop(["Mobile iOS", "Mobile Android"]).mean()
    assert abs(mobile - 33.0) < 1.5, f"mobile {mobile:.1f}%, documented ~33%"
    assert abs(others - 28.0) < 1.5, f"others {others:.1f}%, documented ~28%"
    assert 3.5 <= mobile - others <= 6.5, "the mobile gap is no longer ~5pp"


# --- Q3 · monetisation ---------------------------------------------------


def test_q3_shows_premium_monetising_far_above_free(run_query):
    """Without this, "Premium plans drive revenue" stays an unverified claim."""
    q3 = run_query("Q3").set_index("subscription_plan")
    assert q3.loc["Premium Individual", "rpm"] > q3.loc["Free", "rpm"] * 3
    premium = q3.drop("Free")["revenue"].sum()
    share = premium / q3["revenue"].sum() * 100
    assert 78 <= share <= 86, f"Premium revenue share {share:.1f}%, documented ~82%"


# --- Q4 · retention done right -------------------------------------------


def test_q4_reproduces_the_documented_retention(run_query):
    q4 = run_query("Q4")
    assert abs(one(q4, "retention_pct") - 82.2) < 1.5
    assert abs(one(q4, "churn_pct") - 17.8) < 1.5
    assert abs(one(q4, "retention_pct") + one(q4, "churn_pct") - 100) < 0.2


# --- Q6 · the negative result --------------------------------------------


def test_q6_genre_completion_stays_flat(run_query):
    """Q6 is documented as a NON-finding: if a genre effect appeared, the
    documentation would need to be rewritten as a positive finding."""
    q6 = run_query("Q6")
    col = [c for c in q6.columns if "completion" in c.lower()][0]
    spread = q6[col].max() - q6[col].min()
    assert q6[col].mean() < 100, "completion looks like a percentage >100"
    assert spread < 3.0, f"completion by genre now varies by {spread:.2f}: an effect exists"
    assert 55 <= q6[col].mean() <= 61, (
        f"completion averages {q6[col].mean():.1f}%, documented as ~58%. Flat across "
        f"genres isn't the whole claim — the level itself is quoted too."
    )


def test_q6_spread_matches_the_documented_figure_at_full_scale(run_query_full_scale):
    """business_questions.md names a specific spread — 0.3pp — not just "flat".
    That figure only holds at the repo's real 45,000-user scale: at the
    20,000-user scale the test above runs on, the same near-zero effect
    measures ~0.7pp, more than double, while still comfortably passing the
    generous `< 3.0` bound (which exists to catch a real genre effect
    appearing, not to protect this specific number). This test checks the
    number itself, at the scale it's actually quoted for."""
    q6 = run_query_full_scale("Q6")
    col = [c for c in q6.columns if "completion" in c.lower()][0]
    spread = q6[col].max() - q6[col].min()
    assert spread < 1.0, (
        f"completion by genre spread {spread:.2f}pp at full scale, documented ~0.3pp"
    )


# --- Q8 · the bug that started this file ---------------------------------


def test_q8_does_not_return_a_hundred_percent_every_month(run_query):
    """With an INNER JOIN this query returns 100% everywhere, because the
    join removes from the denominator exactly the users who did not come
    back."""
    q8 = run_query("Q8")
    assert q8["retention_pct"].max() < 99.5, (
        "month-over-month retention ~100%: the denominator is excluding "
        "everyone who didn't come back, which is the only thing this metric measures"
    )


def test_q8_reproduces_the_documented_range(run_query):
    q8 = run_query("Q8")["retention_pct"]
    assert 87 <= q8.min() <= 92, f"minimum {q8.min():.1f}%, documented ~90%"
    assert 94 <= q8.max() <= 99, f"maximum {q8.max():.1f}%, documented ~97%"


def test_q8_does_not_emit_a_trailing_zero_month(run_query):
    """The last month has no following month to compare against: emitting it
    produced a final row at 0.0% that looked like a retention collapse."""
    q8 = run_query("Q8")
    assert (q8["retention_pct"] > 50).all(), (
        f"spurious row at {q8['retention_pct'].min()}%: the last month must not be emitted"
    )
    assert len(q8) == 11, f"{len(q8)} rows, expected 11 (12 months minus the last)"


# --- Q9 · seasonality, normalised ----------------------------------------


def test_q9_normalises_by_active_users(run_query):
    """Raw volume tracks the growth of the user base; seasonality only
    emerges once divided by the users active that month."""
    q9 = run_query("Q9")
    assert q9["active_users"].iloc[7] > q9["active_users"].iloc[0] * 1.5, (
        "the user base no longer grows over the course of the year"
    )
    idx = q9["seasonal_index"]
    assert idx.iloc[5:8].mean() > 110, f"summer peak {idx.iloc[5:8].mean():.0f}"
    assert idx.iloc[11] > 105, f"December {idx.iloc[11]:.0f}"
    assert idx.idxmin() == 1, "the minimum is no longer February"


# --- Q10 · the weekend lift ----------------------------------------------


def test_q10_reproduces_the_documented_weekend_lift(run_query):
    """The defect that motivated actually running the SQL: deriving weekend
    from EXTRACT(DAYOFWEEK) gave -7.8% on one engine and +25.4% on another,
    because day numbering isn't the same. It's now read from dim_time."""
    q10 = run_query("Q10")
    lift = one(q10, "lift_pct")
    assert 22 <= lift <= 29, f"weekend lift {lift:.1f}%, documented ~25%"
    assert one(q10, "weekend_avg") > one(q10, "weekday_avg")


def test_q5_and_q10_agree_on_which_days_are_weekend(run_query):
    """Q5 counts monthly totals, Q10 the per-day average: starting from the
    same definition, the totals have to reconcile."""
    q5, q10 = run_query("Q5"), run_query("Q10")
    we_col = [c for c in q5.columns if "weekend" in c.lower()][0]
    wd_col = [c for c in q5.columns if "weekday" in c.lower()][0]
    total_ratio = q5[we_col].sum() / q5[wd_col].sum()
    # ~104 weekend days against ~261 weekdays: the ratio of totals must stay
    # well below 1 even though the weekend performs better per day.
    assert 0.3 < total_ratio < 0.7, (
        f"weekend/weekday total ratio {total_ratio:.2f}: the two queries aren't "
        f"using the same definition of weekend"
    )
    assert one(q10, "lift_pct") > 0, "Q10 says the weekend performs worse than weekdays"
