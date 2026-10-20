# DATABASE_SCHEMA.md — SQLite

**Engine:** SQLite file at `data/aspectlens.db` (created on first run, seeded from the demo sample). Use SQLAlchemy or plain `sqlite3`; enable `PRAGMA foreign_keys=ON`.

**Deliberately no `users` table.** The app has no accounts or login; it is a public demo. Uploaded data is tied to an `upload_batches` row, not a person. If auth is ever added, add `users` + `owner_id` on `upload_batches` only.

## Tables

### products
| col | type | notes |
|---|---|---|
| id | TEXT PK | e.g. Amazon ASIN / slug |
| name | TEXT NOT NULL | |
| category | TEXT | Electronics, Restaurant… |
| source | TEXT | `amazon`, `semeval`, `upload` |
| review_count | INTEGER DEFAULT 0 | denormalised |

### upload_batches
| col | type | notes |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | |
| created_at | TEXT (ISO 8601) | |
| filename | TEXT | |
| row_count | INTEGER | |
| status | TEXT | `processing` / `done` / `failed` |

### reviews
| col | type | notes |
|---|---|---|
| id | TEXT PK | review id |
| product_id | TEXT FK → products.id | |
| batch_id | INTEGER FK → upload_batches.id NULL | null for seeded data |
| text_display | TEXT NOT NULL | **PII-stripped** original text (offsets refer to this) |
| rating | INTEGER | 1–5, nullable |
| review_date | TEXT | ISO date, nullable |
| overall_label | TEXT | whole-review sentiment (for "aspect vs whole" comparison) |
| processed_at | TEXT | |

No reviewer name, email, phone, or user id is ever stored.

### canonical_aspects
| col | type | notes |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT UNIQUE | Battery, Price, Delivery… |
| domain | TEXT | electronics / restaurant / generic |

### aspect_aliases
| col | type | notes |
|---|---|---|
| id | INTEGER PK | |
| canonical_id | INTEGER FK → canonical_aspects.id | |
| alias | TEXT | lemma, e.g. "battery life", "charge" |
| origin | TEXT | `seed` / `wordnet` / `embedding` |
| UNIQUE(canonical_id, alias) | | |

### aspect_mentions  (the core table)
| col | type | notes |
|---|---|---|
| id | INTEGER PK | |
| review_id | TEXT FK → reviews.id ON DELETE CASCADE | |
| canonical_id | INTEGER FK → canonical_aspects.id | |
| term | TEXT | surface form |
| char_start | INTEGER | offset in `text_display` |
| char_end | INTEGER | |
| sentiment | TEXT CHECK IN ('positive','negative','neutral') | |
| confidence | REAL | 0–1 |
| score | REAL | signed, −1…+1, for averages |
| opinion_words | TEXT | JSON array |
| scorer | TEXT | `vader` / `transformer` / `finetuned` |
| extractor | TEXT | which extraction config produced it |
| snippet | TEXT | clause text for "representative snippets" |

### evaluation_runs  (optional index; files in eval/results are the source of truth)
| col | type | notes |
|---|---|---|
| id | INTEGER PK | |
| run_at | TEXT | |
| name | TEXT | e.g. `ablation_extraction` |
| result_path | TEXT | path to JSON/CSV |

## Indexes
```sql
CREATE INDEX idx_reviews_product ON reviews(product_id);
CREATE INDEX idx_reviews_date ON reviews(review_date);
CREATE INDEX idx_mentions_review ON aspect_mentions(review_id);
CREATE INDEX idx_mentions_aspect ON aspect_mentions(canonical_id, sentiment);
```

## Key queries (aggregation)
**Per-product aspect summary**
```sql
SELECT ca.name AS aspect,
       COUNT(*) AS mentions,
       ROUND(100.0*SUM(m.sentiment='positive')/COUNT(*),1) AS pos_pct,
       ROUND(100.0*SUM(m.sentiment='negative')/COUNT(*),1) AS neg_pct,
       ROUND(AVG(m.score),3) AS avg_score
FROM aspect_mentions m
JOIN reviews r ON r.id = m.review_id
JOIN canonical_aspects ca ON ca.id = m.canonical_id
WHERE r.product_id = :pid
GROUP BY ca.id
HAVING mentions >= :min_mentions
ORDER BY mentions DESC;
```
**Monthly trend** — same join, `GROUP BY substr(r.review_date,1,7), ca.id`.
**Top snippets** — order by `confidence DESC` per sentiment, `LIMIT 3`.

## Rules
- Always show `mentions` beside percentages (small samples must not be over-read).
- Parameterised queries only (no string-built SQL).
- Demo DB is rebuilt from `data/demo_sample.*` if missing; never commit the `.db` file if it exceeds repo limits.
- Uploads: capped rows; `batch_id` lets old uploads be purged on a schedule.

## Migration approach
Single `init_db()` that runs `CREATE TABLE IF NOT EXISTS`. Keep a `schema_version` pragma (`PRAGMA user_version`) and bump when changing tables.
