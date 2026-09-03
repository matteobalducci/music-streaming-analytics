# Business Questions & Findings

This project treats the dataset as the **digital twin of a streaming platform** and answers the questions a product-analytics team would actually ask. Figures come from the full 1.22M-event dataset (2024).

---

## 1. Is our recommender serving music people want? (Discovery Efficiency)

**Finding:** Algorithmic recommendations are skipped **~42%** of the time, versus **~22%** for Editorial and Search.

**So what:** Volume hides a retention problem. If two-fifths of algorithmically-served streams are abandoned in the first seconds, the recommender is padding stream counts with mismatched content. The lever is model relevance, not more recommendations.

![skip by source](screenshots/skip_rate_by_source.png)

---

## 2. Where do skips happen? (Device experience)

**Finding:** Mobile (iOS/Android) skips **~33%** vs **~28%** on desktop/tablet/speaker.

**So what:** The skip problem is concentrated on mobile, not on any one country — so the fix is a better on-device recommender and mobile UX, not geo-targeted marketing.

![skip by device](screenshots/skip_rate_by_device.png)

---

## 3. Where does the money come from? (Monetization)

**Finding:** Premium tiers are **55%** of users but **82%** of revenue; Free is **45%** of users and **18%** of revenue. Revenue per stream runs **~0.0079** for Premium Individual against **~0.0018** for Free — the ad-funded tier monetises at roughly a quarter of the subscription tiers.

**So what:** Growing users without growing RPM would signal low-value acquisition. Tracking both together keeps volume and monetization honest. See `sql/analysis/business_questions.sql` Q3.

---

## 4. Are we keeping users? (Retention — done right)

**Finding:** A naïve `active / signed-up` KPI reads **~96%** — but that is **reach, not retention**. Using `churn_date`, **~18%** of users churn within the year → **real retention ≈ 82%**, and month-over-month retention sits at **90–97%**, lowest in **February** and dipping again in **September** (Q8).

**So what:** The 96% number would hide a real 18% churn in an executive review. The corrected measure (and the DAX for it) is the difference between a metric that *looks* good and one that *drives* decisions. See Q4.

---

## 5. When do we need capacity and content? (Seasonality)

**Finding:** Raw monthly volume is **not** a seasonality signal — it is dominated by the growing
user base. August has roughly three times January's streams mostly because it has twice the active
users. Dividing by active users per month (Q9), the seasonal pattern appears: **summer +16%**,
**December +11%**, **February −19%** against the yearly average. Weekend days carry **+26%** more
streams than weekdays (Q10).

**So what:** Infrastructure capacity and editorial calendars should be pre-loaded ahead of these
windows — but the normalisation matters more than the finding. Reading raw monthly volume as
seasonality would credit summer campaigns for growth that was just accumulated signups.

![seasonality](screenshots/monthly_seasonality.png)

---

## 6. Volume vs quality by genre — a negative result

**Finding:** Ranking genres by *completion rate* rather than raw streams **does not** reorder them
meaningfully. Completion — `listen_duration_sec / total_duration_sec`, as Q6 computes it — sits between
**57.9% and 58.2%** across every genre: a 0.3pp spread, inside sampling noise on 1.2M events. Sorting by it reshuffles the top three, but the reshuffle is
random.

**So what:** This is reported because it is the answer, not because it is the answer anyone wanted.
Genre is **not** where the engagement problem lives: skip rate varies by 20pp across `stream_source`
and by 5pp across device, and by essentially nothing across genre. Editorial effort aimed at
"promoting the genres people finish" would be optimising noise. The levers are the recommender
(Q1) and the mobile experience (Q2).

*A note on the data:* the generator sets skip probability from source and device only, so the
absence of a genre effect is by construction, not a discovery about music. It is kept here because
a synthetic dataset should not be read as evidence of something it was never built to contain —
and `tests/test_headline_metrics.py` now asserts the spread stays inside noise, so the claim cannot
quietly turn positive.

---

## 7. Subscription mix

**Finding:** Free **~45%** · Premium Individual **~30%** · Premium Student **~15%** · Premium Family **~10%** of active users.

**So what:** Free is the single largest segment — the conversion funnel starts there.

![subscription mix](screenshots/subscription_mix.png)
