# Business Questions & Findings

This project treats the dataset as the **digital twin of a streaming platform** and answers the questions a product-analytics team would actually ask. Every figure below comes from the full 1.2M-event dataset (2024).

---

## 1. Is our recommender serving music people want? (Discovery Efficiency)

**Finding:** Algorithmic recommendations are skipped **~40%** of the time, versus **~15%** for Editorial, Radio and Search.

**So what:** Volume alone hides a retention problem. If two-fifths of algorithmically-served streams are abandoned in the first seconds, the recommender is padding stream counts with mismatched content. The lever is model relevance, not more recommendations.

![skip by source](screenshots/skip_rate_by_source.png)

---

## 2. Volume vs quality by genre

**Finding:** High stream volume does not equal high engagement. Ranking genres by *completion rate* rather than raw streams reorders the "top performers."

**So what:** A content team optimizing for long-term retention should weight editorial support toward genres with high completion and low skip, not just the loudest volume.

---

## 3. Is growth driven by new drops or the back catalog? (Frontline vs Catalog)

**Finding:** Frontline (new releases) account for **~35%** of streams; catalog carries the remaining **~65%**.

**So what:** Labels and platforms run different margin and marketing strategies for new hits vs classics. A catalog-heavy consumption mix means growth is more resilient but new-release marketing has room to convert.

![frontline vs catalog](screenshots/frontline_catalog.png)

---

## 4. When do we need capacity and content? (Seasonality)

**Finding:** Listening peaks in **summer (+~40%)** and **December (+~30%)**, with a consistent **weekend lift**.

**So what:** Infrastructure capacity planning and editorial calendars (summer playlists, holiday campaigns) should be pre-loaded ahead of these windows.

![seasonality](screenshots/monthly_seasonality.png)

---

## 5. Can we detect a hit before it's obvious? (Virality)

**Finding:** Track 50 streams **~14x** its own monthly baseline in October — a clear breakout the window-function query in [`sql/analysis/business_questions.sql`](../sql/analysis/business_questions.sql) (Q5) flags automatically.

**So what:** Automated breakout detection lets editorial and playlist teams ride momentum in days, not weeks.

![viral track](screenshots/viral_track.png)

---

## 6. Peak listening hours (Circadian)

**Finding:** Streams peak in the evening (19:00–20:00) and around midnight.

**So what:** Push-notification timing and new-release drop times should target these windows.

---

## 7. Subscribers vs free users

**Finding:** ~35% of the base are subscribers; behavioural differences in streams-per-user and skip rate inform the conversion funnel.

**So what:** Understanding where free-user behaviour diverges from subscriber behaviour is the starting point for a conversion strategy.
