"""
Reproducible generator for the music-streaming star schema.

Produces the same 5-table shape as the analysed dataset — a fact table plus
four dimensions (users, tracks, platform, time) — calibrated to realistic
streaming dynamics: seasonality (summer & December lift), weekend lift, an
algorithmic-vs-editorial skip gap, a mobile skip lift, and ~18% user churn.

Output: F_Streams.csv, D_Users.csv, D_Tracks.csv, D_Platform.csv, D_Time.csv

Usage:
    python scripts/generate_datasets.py --out data/ --users 45000 --seed 42
"""

import argparse
import os

import numpy as np
import pandas as pd

YEAR = 2024
COUNTRIES = ["USA", "Italy", "UK", "France", "Brazil", "Germany"]
PLANS = ["Free", "Premium Individual", "Premium Student", "Premium Family"]
PLAN_P = [0.448, 0.299, 0.152, 0.101]
CHANNELS = ["Social Media Ads", "App Store", "Influencer Referral", "Organic Search"]
GENRES = ["Electronic", "Hip Hop", "Pop", "Classical", "Indie", "Rock", "Reggaeton"]
GENRE_P = [0.20, 0.15, 0.14, 0.14, 0.13, 0.12, 0.12]
PLATFORMS = ["Spotify", "Apple Music", "YouTube Music", "SoundCloud"]
DEVICES = ["Mobile iOS", "Mobile Android", "Tablet", "Desktop", "Smart Speaker"]
CONN = ["Wifi", "Cellular", "Offline"]
CONN_P = [0.60, 0.30, 0.10]
SOURCES = ["Algorithmic", "Editorial", "Search"]
SOURCE_P = [0.40, 0.20, 0.40]

# Skip probability by discovery source — the dataset's defining signal.
# BASE skip probabilities, before MOBILE_SKIP_LIFT is added on top. Mobile is
# 2 of 5 device types, so the lift raises each realised rate by 0.4 * 0.05 = 2pp:
#   Algorithmic 0.40 -> 42%   Editorial 0.20 -> 22%   Search 0.20 -> 22%
# which are the figures the README and the dashboard quote.
#
# FIX 2026-09-03: these had been set to the *realised* values (0.42/0.22/0.22),
# which double-counted the lift and produced 44%/24%/24% — silently breaking the
# headline numbers in the README. tests/test_headline_metrics.py now locks them.
SKIP_BY_SOURCE = {"Algorithmic": 0.40, "Editorial": 0.20, "Search": 0.20}
MOBILE_SKIP_LIFT = 0.05          # mobile devices skip a bit more
CHURN_RATE = 0.18
STREAMS_PER_USER = 27
MONTH_MULT = {1: .85, 2: .82, 3: .9, 4: .95, 5: 1.0, 6: 1.15,
              7: 1.25, 8: 1.2, 9: .95, 10: .95, 11: .95, 12: 1.1}  # summer + Dec lift
WEEKEND_LIFT = 1.25

# Ricavo medio per stream, per piano. Il Free monetizza con la pubblicita' —
# pochi millesimi per ascolto; i piani Premium ripartiscono l'abbonamento sugli
# ascolti del mese, quindi rendono molto di piu' per stream. Senza questa
# differenza la Q3 non puo' dire nulla su quale piano genera i ricavi.
REVENUE_PER_STREAM = {
    "Free": 0.0018,
    "Premium Student": 0.0052,
    "Premium Family": 0.0061,
    "Premium Individual": 0.0079,
}
ROYALTY_SHARE = 0.68   # quota del ricavo che va alle etichette
# Listening hour is close to uniform in the analysed dataset (no circadian dip) —
# match that rather than inventing a pattern the real data doesn't show.
HOUR_W = np.ones(24)


def build_platform():
    return pd.DataFrame({"platform_id": range(1, 5), "service_name": PLATFORMS})


def build_time(year, rng):
    days = pd.date_range(f"{year}-01-01", f"{year}-12-31", freq="D")
    return pd.DataFrame({
        "time_key": days.strftime("%Y-%m-%d"),
        "year": days.year, "month": days.month,
        "day_of_week": days.day_name(),
        "is_weekend": days.dayofweek >= 5,
    })


def build_users(n, rng):
    signup = pd.to_datetime(f"{YEAR-1}-08-01") + pd.to_timedelta(rng.integers(0, 400, n), "D")
    # FIX 2026-09-03: `churned` era calcolato e mai usato — la riga successiva
    # sovrascriveva la serie per TUTTI gli utenti, dando a ognuno una data di
    # abbandono dentro l'anno. La Q4 del repo, che misura la retention come
    # `churn_date IS NULL OR churn_date > '2024-12-31'`, restituiva quindi il 27%
    # invece dell'82% documentato e presente nei dati caricati su BigQuery.
    # Nessun controllo se ne accorgeva: il dataset si generava, i controlli di
    # qualita' passavano, l'SQL girava. Solo la conclusione era falsa.
    churned = rng.random(n) < CHURN_RATE

    # Chi abbandona lo fa entro la finestra di analisi; chi resta riceve una data
    # oltre l'anno — come nel dataset caricato, dove churn_date e' valorizzata per
    # tutti ma solo il 17,7% cade entro il 2024.
    # L'abbandono e' concentrato all'inizio: chi si iscrive e non si affeziona
    # se ne va nelle prime settimane, non a meta' del secondo anno. Una
    # distribuzione esponenziale riproduce quella forma — e riproduce anche i
    # dati caricati, dove il 44% di chi abbandona lo fa entro aprile. Con un
    # offset uniforme la retention di aprile leggeva 96,3% contro il 92,3%
    # della dashboard.
    offset = np.clip(rng.exponential(110, n), 20, 500).astype(int)
    churn = (signup + pd.to_timedelta(offset, "D")).to_numpy()
    year_end = np.datetime64(f"{YEAR}-12-31")
    next_year = np.datetime64(f"{YEAR + 1}-01-15")

    churn = np.where(
        churned,
        np.minimum(churn, year_end),                                  # abbandona: dentro l'anno
        np.maximum(churn, next_year) + rng.integers(0, 300, n).astype("timedelta64[D]"),
    )
    churn = pd.DatetimeIndex(churn)

    return pd.DataFrame({
        "user_id": range(1, n + 1),
        "country": rng.choice(COUNTRIES, n),
        "signup_date": signup.strftime("%Y-%m-%d"),
        "subscription_plan": rng.choice(PLANS, n, p=PLAN_P),
        "signup_channel": rng.choice(CHANNELS, n),
        "churn_date": churn.strftime("%Y-%m-%d"),
    }), churned


def build_tracks(n, rng):
    return pd.DataFrame({
        "track_id": range(1, n + 1),
        "track_title": [f"Track {i}" for i in range(1, n + 1)],
        "artist_id": rng.integers(1, 41, n),
        "main_genre": rng.choice(GENRES, n, p=GENRE_P),
        "release_date": (pd.to_datetime("2022-09-01") + pd.to_timedelta(rng.integers(0, 760, n), "D")).strftime("%Y-%m-%d"),
        "bpm": rng.integers(66, 176, n),
        "energy": rng.uniform(0.30, 0.95, n).round(2),
        "valence": rng.uniform(0.10, 0.88, n).round(2),
        "danceability": rng.uniform(0.40, 0.88, n).round(2),
        "total_duration_sec": rng.integers(150, 320, n),
    })


def build_streams(n_users, tracks, time_dim, churned, signup, churn_dates,
                  plans_by_user, rng):
    days = pd.to_datetime(time_dim["time_key"])
    w = days.dt.month.map(MONTH_MULT).to_numpy(dtype=float, copy=True)
    w *= np.where(days.dt.dayofweek >= 5, WEEKEND_LIFT, 1.0)
    w /= w.sum()

    total = n_users * STREAMS_PER_USER

    # FIX 2026-09-03: `churned` era il terzo parametro morto di questo file —
    # arrivava nella firma e non veniva mai usato, quindi gli stream si
    # distribuivano uniformemente su TUTTI gli utenti e ognuno ne riceveva
    # almeno uno. Il KPI "attivi / iscritti" leggeva quindi il 100%.
    #
    # Q4 costruisce il suo argomento proprio su quel numero: «il KPI ingenuo
    # legge ~97%, ma quella e' portata, non retention». Con il 100% l'esempio
    # perdeva il suo contrasto piu' netto, e non corrispondeva ai dati caricati
    # (97,3%). Chi abbandona ascolta meno, e qualcuno non compare affatto.
    # Il peso di un utente e' la frazione dell'anno in cui e' stato attivo:
    # chi si iscrive a meta' anno, o chi abbandona a gennaio, ascolta meno. Chi
    # ha gia' abbandonato prima che l'anno cominci non compare affatto, ed e'
    # esattamente cosi' che il KPI "attivi / iscritti" scende sotto il 100%.
    year_start = np.datetime64(f"{YEAR}-01-01")
    year_end_np = np.datetime64(f"{YEAR}-12-31")
    span = (year_end_np - year_start).astype(int) + 1

    inizio = np.maximum(signup.to_numpy().astype("datetime64[D]"), year_start)
    # Il giorno dell'abbandono e' il primo giorno NON piu' attivo: la finestra
    # si chiude il giorno prima, cosi' nessuno stream cade su o dopo il churn.
    fine = np.minimum(churn_dates.to_numpy().astype("datetime64[D]")
                      - np.timedelta64(1, "D"), year_end_np)
    giorni_attivi = np.clip((fine - inizio).astype(int) + 1, 0, span)

    user_weight = giorni_attivi.astype(float)
    if user_weight.sum() == 0:
        user_weight = np.ones(n_users)
    user_weight = user_weight / user_weight.sum()

    # L'utente si sceglie PRIMA della data, perche' la data deve cadere nella
    # sua finestra di attivita'.
    #
    # FIX 2026-09-03: prima le date venivano estratte globalmente e l'utente
    # assegnato dopo, in modo indipendente. Il risultato era che il 13,7% degli
    # stream precedeva l'iscrizione dell'utente e il 2,4% avveniva dopo il suo
    # abbandono. Una tabella dei fatti in cui un evento precede l'esistenza
    # dell'utente non e' difendibile, e rende inaffidabile qualsiasi analisi
    # temporale — comprese proprio la retention e la stagionalita' che il
    # progetto documenta.
    user_idx = rng.choice(n_users, total, p=user_weight)

    # Finestra ammessa per ciascuno stream, in indici di giorno dell'anno.
    primo = np.searchsorted(days.to_numpy(), inizio.astype("datetime64[ns]"))
    ultimo = np.searchsorted(days.to_numpy(), fine.astype("datetime64[ns]"))
    lo, hi = primo[user_idx], np.maximum(ultimo[user_idx], primo[user_idx])

    # Si estrae dalla distribuzione stagionale e si ripesca solo cio' che cade
    # fuori finestra: dopo pochi giri restano pochissimi casi, che si assegnano
    # uniformemente dentro la finestra. Cosi' la stagionalita' resta intatta per
    # la stragrande maggioranza degli eventi senza costruire una distribuzione
    # separata per ognuno dei 45.000 utenti.
    day_idx = rng.choice(len(days), total, p=w)
    for _ in range(12):
        fuori = (day_idx < lo) | (day_idx > hi)
        if not fuori.any():
            break
        day_idx[fuori] = rng.choice(len(days), int(fuori.sum()), p=w)
    fuori = (day_idx < lo) | (day_idx > hi)
    if fuori.any():
        day_idx[fuori] = lo[fuori] + (rng.random(int(fuori.sum()))
                                      * (hi[fuori] - lo[fuori] + 1)).astype(int)
    day_idx = np.clip(day_idx, lo, hi)

    listen_date = days.dt.strftime("%Y-%m-%d").to_numpy()[day_idx]
    listen_hour = rng.choice(24, total, p=HOUR_W / HOUR_W.sum())

    # popularity-weighted track choice
    pop = 1.0 / np.arange(1, len(tracks) + 1) ** 0.35
    pop /= pop.sum()
    track_id = rng.choice(tracks["track_id"].to_numpy(), total, p=pop)

    source = rng.choice(SOURCES, total, p=SOURCE_P)
    device = rng.choice(DEVICES, total)
    is_mobile = np.isin(device, ["Mobile iOS", "Mobile Android"])

    skip_p = np.vectorize(SKIP_BY_SOURCE.get)(source) + is_mobile * MOBILE_SKIP_LIFT
    is_skipped = rng.random(total) < skip_p
    is_liked = rng.random(total) < np.where(is_skipped, 0.03, 0.20)

    durations = tracks.set_index("track_id")["total_duration_sec"]
    full = durations.reindex(track_id).to_numpy()
    listen_dur = np.where(is_skipped,
                          (rng.uniform(2, 30, total)).astype(int),
                          (full * rng.uniform(0.6, 1.0, total)).astype(int))

    # FIX 2026-09-03: `revenue_generated` era estratto dalla stessa uniforme per
    # tutti, indipendentemente dal piano — quindi la conclusione «i piani Premium
    # guidano i ricavi» non era misurabile sui dati, e la Q3 sommava lo stesso
    # ricavo anche agli utenti Free. Ora il ricavo per stream dipende dal piano:
    # il Free monetizza con la pubblicita' (poco per stream), il Premium con
    # l'abbonamento ripartito sugli ascolti.
    piano_utente = plans_by_user[user_idx]
    base = np.vectorize(REVENUE_PER_STREAM.get)(piano_utente)
    revenue = (base * rng.uniform(0.75, 1.25, total)).round(5)

    # Il costo di royalty si paga solo su un ascolto vero, non su uno skip.
    royalty = np.where(is_skipped, 0.0, revenue * ROYALTY_SHARE).round(5)
    return pd.DataFrame({
        "user_id": user_idx + 1,
        "track_id": track_id,
        "platform_id": rng.integers(1, 5, total),
        "listen_date": listen_date,
        "listen_hour": listen_hour,
        "device_type": device,
        "connection_type": rng.choice(CONN, total, p=CONN_P),
        "stream_source": source,
        "is_skipped": is_skipped,
        "is_liked": is_liked,
        "listen_duration_sec": listen_dur,
        "royalty_cost": royalty,
        "revenue_generated": revenue,
    })


def main():
    parser = argparse.ArgumentParser(description="Generate the streaming star schema")
    parser.add_argument("--out", default="data/")
    parser.add_argument("--users", type=int, default=45000)
    parser.add_argument("--tracks", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    os.makedirs(args.out, exist_ok=True)

    platform = build_platform()
    time_dim = build_time(YEAR, rng)
    users, churned = build_users(args.users, rng)
    tracks = build_tracks(args.tracks, rng)
    streams = build_streams(args.users, tracks, time_dim, churned,
                            pd.to_datetime(users['signup_date']),
                            pd.to_datetime(users['churn_date']),
                            users['subscription_plan'].to_numpy(), rng)

    platform.to_csv(os.path.join(args.out, "D_Platform.csv"), index=False)
    time_dim.to_csv(os.path.join(args.out, "D_Time.csv"), index=False)
    users.to_csv(os.path.join(args.out, "D_Users.csv"), index=False)
    tracks.to_csv(os.path.join(args.out, "D_Tracks.csv"), index=False)
    streams.to_csv(os.path.join(args.out, "F_Streams.csv"), index=False)

    print(f"Generated {len(streams):,} streams for {args.users:,} users ({YEAR}) -> {args.out}")
    print(f"Overall skip rate: {streams['is_skipped'].mean():.1%} | "
          f"algorithmic: {streams.loc[streams.stream_source=='Algorithmic','is_skipped'].mean():.1%}")


if __name__ == "__main__":
    main()
