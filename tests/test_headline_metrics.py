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


# --- portata contro retention, stagionalita', e un risultato negativo -----


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
    """Q4 poggia sul contrasto fra il KPI ingenuo e la retention vera. Se ogni
    utente ha almeno uno stream il KPI legge 100% e il contrasto sparisce —
    ed e' quello che succedeva quando `churned` non veniva passato a
    build_streams. Chi abbandona presto non deve comparire affatto.
    """
    streams, users, _ = both
    naive = streams.user_id.nunique() / len(users) * 100
    assert 96 <= naive <= 99.5, f"KPI ingenuo {naive:.1f}%, atteso ~99%"


def test_the_gap_between_reach_and_retention_is_the_finding(both):
    """Il numero che conta non e' il KPI ne' la retention, ma la distanza fra i
    due: e' l'intero argomento della Q4."""
    streams, users, _ = both
    naive = streams.user_id.nunique() / len(users) * 100
    real = (pd.to_datetime(users.churn_date) > "2024-12-31").mean() * 100
    assert naive - real > 12, (
        f"lo scarto e' sceso a {naive - real:.1f}pp: senza distanza fra portata e "
        f"retention la Q4 non dimostra piu' niente"
    )


def test_raw_monthly_volume_tracks_user_growth_not_season(both):
    """Il volume grezzo NON e' un segnale stagionale: cresce con la base utenti.
    Documentarlo come stagionalita' attribuirebbe alle campagne estive una
    crescita che erano solo iscrizioni accumulate."""
    streams, _, _ = both
    per_mese = streams.assign(m=pd.to_datetime(streams.listen_date).dt.month).groupby("m").size()
    assert per_mese[8] > per_mese[1] * 2, (
        "agosto non ha piu' molti piu' stream di gennaio: la crescita della base "
        "utenti e' sparita dal modello, e la Q5 va riscritta"
    )


def test_seasonality_appears_once_normalised_by_active_users(both):
    """Divisa per utenti attivi, la stagionalita' emerge: estate +18%,
    dicembre +14%, febbraio -23%."""
    streams, users, _ = both
    d = pd.to_datetime(streams.listen_date)
    signup = pd.to_datetime(users.signup_date)
    churn = pd.to_datetime(users.churn_date)

    indice = {}
    for m in range(1, 13):
        inizio = pd.Timestamp(2024, m, 1)
        fine = inizio + pd.offsets.MonthEnd(0)
        attivi = ((signup <= fine) & (churn > inizio)).sum()
        indice[m] = (d.dt.month == m).sum() / max(attivi, 1)
    media = sum(indice.values()) / 12
    idx = {m: v / media * 100 for m, v in indice.items()}

    assert sum(idx[m] for m in (6, 7, 8)) / 3 > 110, "picco estivo sparito"
    assert idx[12] > 108, "picco di dicembre sparito"
    assert min(idx, key=idx.get) == 2, "il minimo non e' piu' febbraio"


def test_weekends_carry_about_a_quarter_more_streams(both):
    streams, _, _ = both
    d = pd.to_datetime(streams.listen_date)
    per_giorno = streams.groupby([d.dt.date, (d.dt.dayofweek >= 5).values]).size()
    per_giorno.index.names = ["data", "weekend"]
    per_giorno = per_giorno.reset_index(name="n")
    lift = (per_giorno[per_giorno.weekend].n.mean()
            / per_giorno[~per_giorno.weekend].n.mean() - 1) * 100
    assert 20 <= lift <= 32, f"lift weekend {lift:.1f}%, atteso ~26%"


def test_genre_completion_stays_inside_noise(both):
    """Q6 e' un risultato NEGATIVO e va tenuto tale.

    Il generatore ricava la probabilita' di skip da sorgente e dispositivo, mai
    dal genere: la completion per genere e' quindi identica per costruzione e
    ogni riordino e' rumore campionario. Se qualcuno introduce un effetto di
    genere, questo test fallisce e la Q6 va riscritta come risultato positivo —
    invece di restare una conclusione che i dati non sostengono.
    """
    streams, _, tracks = both
    m = streams.merge(tracks[["track_id", "main_genre", "total_duration_sec"]], on="track_id")
    # La completion e' la frazione di brano ascoltata, come la calcola la Q6 —
    # NON "non saltato". Confonderle e' l'errore che questo test aveva dentro
    # alla prima stesura, e che documentava 70% al posto del 58% reale.
    m["completion"] = m.listen_duration_sec / m.total_duration_sec
    per_genere = m.groupby("main_genre").completion.mean()
    spread = (per_genere.max() - per_genere.min()) * 100
    assert 55 <= per_genere.mean() * 100 <= 61, (
        f"completion media {per_genere.mean() * 100:.1f}%, documentata ~58%")
    assert spread < 3.0, (
        f"la completion per genere varia di {spread:.1f}pp: ora esiste un effetto "
        f"di genere e la Q6 va riscritta — oggi e' documentata come non-risultato"
    )


# --- integrita' temporale e monetizzazione -------------------------------


def test_no_stream_happens_outside_the_users_lifetime(both):
    """Una tabella dei fatti in cui un evento precede l'esistenza dell'utente
    non e' difendibile, e rende inaffidabile ogni analisi temporale — comprese
    la retention e la stagionalita' che questo progetto documenta.

    Prima del 2026-09-03 il 13,7% degli stream precedeva l'iscrizione e il 2,4%
    seguiva l'abbandono: le date venivano estratte globalmente e l'utente
    assegnato dopo, in modo indipendente.
    """
    streams, users, _ = both
    m = streams.merge(users[["user_id", "signup_date", "churn_date"]], on="user_id")
    d = pd.to_datetime(m.listen_date)
    prima = (d < pd.to_datetime(m.signup_date)).mean() * 100
    dopo = (d >= pd.to_datetime(m.churn_date)).mean() * 100
    assert prima == 0, f"{prima:.2f}% degli stream precede l'iscrizione dell'utente"
    assert dopo == 0, f"{dopo:.2f}% degli stream avviene dopo l'abbandono"


def test_revenue_actually_depends_on_the_plan(both):
    """La conclusione «i piani Premium guidano i ricavi» dev'essere misurabile.
    Fino al 2026-09-03 revenue_generated veniva estratto dalla stessa uniforme
    per tutti, quindi quella frase non poggiava su nulla."""
    streams, users, _ = both
    m = streams.merge(users[["user_id", "subscription_plan"]], on="user_id")
    per_stream = m.groupby("subscription_plan").revenue_generated.mean()
    assert per_stream["Premium Individual"] > per_stream["Free"] * 3, (
        "il Premium non rende piu' del Free per stream: la Q3 non dimostra niente"
    )
    quota = m.groupby("subscription_plan").revenue_generated.sum()
    premium = quota[quota.index != "Free"].sum() / quota.sum() * 100
    assert 78 <= premium <= 86, f"quota ricavi Premium {premium:.1f}%, documentata ~82%"


def test_royalty_is_only_paid_on_a_real_listen(both):
    """Non si pagano diritti su un brano saltato dopo due secondi."""
    streams, _, _ = both
    assert streams[streams.is_skipped == 1].royalty_cost.max() == 0
    assert streams[streams.is_skipped == 0].royalty_cost.min() > 0
