-- =====================================================================
-- Music Streaming Analytics — Business questions answered in SQL
-- Dialect: BigQuery Standard SQL
-- Grain of fct_streams: one row per listening event
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q1. DISCOVERY EFFICIENCY
-- Is the recommender serving music users want, or padding volume with
-- content they skip? Expectation: algorithmic skip rate >> user-driven.
-- ---------------------------------------------------------------------
SELECT
  stream_source,
  COUNT(*)                                       AS streams,
  ROUND(AVG(CAST(is_skipped AS INT64)) * 100, 1) AS skip_rate_pct,
  ROUND(AVG(CAST(is_liked  AS INT64)) * 100, 2)  AS like_rate_pct
FROM `streaming.fct_streams`
GROUP BY stream_source
ORDER BY skip_rate_pct DESC;


-- ---------------------------------------------------------------------
-- Q2. WHERE DO SKIPS HAPPEN — by device
-- Mobile vs desktop/speaker. Informs where to invest in UX / recommender.
-- ---------------------------------------------------------------------
SELECT
  device_type,
  COUNT(*)                                       AS streams,
  ROUND(AVG(CAST(is_skipped AS INT64)) * 100, 1) AS skip_rate_pct
FROM `streaming.fct_streams`
GROUP BY device_type
ORDER BY skip_rate_pct DESC;


-- ---------------------------------------------------------------------
-- Q3. MONETIZATION — revenue & RPM by subscription plan
-- Which plans drive revenue, and what is revenue per 1k active users?
-- ---------------------------------------------------------------------
SELECT
  u.subscription_plan,
  COUNT(DISTINCT s.user_id)                                    AS active_users,
  COUNT(*)                                                     AS streams,
  ROUND(SUM(s.revenue_generated), 2)                           AS revenue,
  ROUND(SUM(s.revenue_generated) / COUNT(DISTINCT s.user_id) * 1000, 2) AS rpm
FROM `streaming.fct_streams` s
JOIN `streaming.dim_user`    u USING (user_id)
GROUP BY u.subscription_plan
ORDER BY revenue DESC;


-- ---------------------------------------------------------------------
-- Q4. RETENTION / CHURN (done right)
-- The dashboard KPI conflates reach with retention. Real retention uses
-- churn_date: share of users still active at year end.
-- ---------------------------------------------------------------------
SELECT
  COUNT(*)                                                              AS signed_up,
  COUNTIF(churn_date IS NULL OR churn_date > DATE '2024-12-31')         AS retained_year_end,
  ROUND(COUNTIF(churn_date IS NULL OR churn_date > DATE '2024-12-31')
        / COUNT(*) * 100, 1)                                            AS retention_pct,
  ROUND(COUNTIF(churn_date <= DATE '2024-12-31') / COUNT(*) * 100, 1)   AS churn_pct
FROM `streaming.dim_user`;


-- ---------------------------------------------------------------------
-- Q5. SEASONALITY — monthly volume with weekend lift
-- ---------------------------------------------------------------------
SELECT
  d.month,
  COUNTIF(NOT d.is_weekend) AS weekday_streams,
  COUNTIF(d.is_weekend)     AS weekend_streams,
  COUNT(*)                  AS total_streams
FROM `streaming.fct_streams` s
JOIN `streaming.dim_time`    d ON s.listen_date = d.time_key
GROUP BY d.month
ORDER BY d.month;


-- ---------------------------------------------------------------------
-- Q6. CONTENT QUALITY by genre — completion vs volume
-- ---------------------------------------------------------------------
SELECT
  t.main_genre,
  COUNT(*)                                                        AS streams,
  ROUND(AVG(CAST(s.is_skipped AS INT64)) * 100, 1)               AS skip_rate_pct,
  ROUND(AVG(s.listen_duration_sec / t.total_duration_sec) * 100, 1) AS avg_completion_pct
FROM `streaming.fct_streams` s
JOIN `streaming.dim_track`   t USING (track_id)
GROUP BY t.main_genre
ORDER BY streams DESC;


-- ---------------------------------------------------------------------
-- Q7. CIRCADIAN LISTENING — peak hours for push/editorial timing
-- ---------------------------------------------------------------------
SELECT
  listen_hour,
  COUNT(*)                                       AS streams,
  ROUND(AVG(CAST(is_skipped AS INT64)) * 100, 1) AS skip_rate_pct
FROM `streaming.fct_streams`
GROUP BY listen_hour
ORDER BY listen_hour;


-- ---------------------------------------------------------------------
-- Q8. RETENTION MESE SU MESE
-- Aggiunta 2026-09-03: docs/business_questions.md citava un intervallo
-- mese-su-mese e un calo stagionale che NESSUNA query calcolava. Un numero
-- documentato senza query dietro e' un'affermazione, non un risultato.
--
-- ATTENZIONE (bug corretto lo stesso giorno): con un INNER JOIN fra il mese
-- precedente e quello corrente il risultato e' sempre 100%, perche' il join
-- elimina dal DENOMINATORE proprio gli utenti che non sono tornati — cioe'
-- l'unica cosa che la retention misura. Il denominatore dev'essere il mese
-- precedente per intero.
-- ---------------------------------------------------------------------
WITH attivi_per_mese AS (
  SELECT DISTINCT
    DATE_TRUNC(listen_date, MONTH) AS mese,
    user_id
  FROM `streaming.F_Streams`
)
SELECT
  DATE_ADD(prev.mese, INTERVAL 1 MONTH)                               AS mese,
  COUNT(DISTINCT prev.user_id)                                        AS attivi_mese_prec,
  COUNT(DISTINCT cur.user_id)                                         AS tornati,
  ROUND(COUNT(DISTINCT cur.user_id)
        / NULLIF(COUNT(DISTINCT prev.user_id), 0) * 100, 1)           AS retention_pct
FROM attivi_per_mese AS prev
LEFT JOIN attivi_per_mese AS cur
  ON cur.user_id = prev.user_id
 AND cur.mese = DATE_ADD(prev.mese, INTERVAL 1 MONTH)
GROUP BY prev.mese
ORDER BY mese;


-- ---------------------------------------------------------------------
-- Q9. STAGIONALITA' NORMALIZZATA PER UTENTE ATTIVO
-- Aggiunta 2026-09-03. Il volume grezzo mensile e' dominato dalla CRESCITA
-- della base utenti, non dalla stagione: gli stream di agosto sono il triplo
-- di quelli di gennaio soprattutto perche' ci sono il doppio degli utenti.
-- La stagionalita' si vede solo dividendo per gli utenti attivi in quel mese.
-- ---------------------------------------------------------------------
WITH per_mese AS (
  SELECT
    DATE_TRUNC(listen_date, MONTH) AS mese,
    COUNT(*)                       AS stream,
    COUNT(DISTINCT user_id)        AS utenti_attivi
  FROM `streaming.F_Streams`
  GROUP BY mese
)
SELECT
  mese,
  stream,
  utenti_attivi,
  ROUND(stream / utenti_attivi, 2)                                    AS stream_per_utente,
  ROUND((stream / utenti_attivi)
        / AVG(stream / utenti_attivi) OVER () * 100, 0)               AS indice_stagionale
FROM per_mese
ORDER BY mese;


-- ---------------------------------------------------------------------
-- Q10. LIFT DEL WEEKEND, PER GIORNO
-- Aggiunta 2026-09-03: la Q5 restituiva i TOTALI di weekend e giorni feriali,
-- che non sono confrontabili — un mese ha ~22 giorni feriali e ~9 di weekend.
-- Il lift richiede la media PER GIORNO.
-- ---------------------------------------------------------------------
WITH per_giorno AS (
  SELECT
    listen_date,
    EXTRACT(DAYOFWEEK FROM listen_date) IN (1, 7) AS is_weekend,
    COUNT(*)                                      AS stream
  FROM `streaming.F_Streams`
  GROUP BY listen_date, is_weekend
)
SELECT
  ROUND(AVG(IF(is_weekend, stream, NULL)), 0)                         AS media_weekend,
  ROUND(AVG(IF(is_weekend, NULL, stream)), 0)                         AS media_feriali,
  ROUND(AVG(IF(is_weekend, stream, NULL))
        / AVG(IF(is_weekend, NULL, stream)) * 100 - 100, 1)           AS lift_pct
FROM per_giorno;
