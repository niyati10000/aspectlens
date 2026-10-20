# PLAN.md — Phased Roadmap

Each phase produces something demoable and has **exit criteria**. Do not start phase N+1 until phase N's exit criteria pass. Commit per phase (`phase-N: …`). Update BRAIN.md Status at the end of each.

## Overview
| # | Phase | Output | Week* |
|---|---|---|---|
| 0 | Plan & approval | Implementation plan + task list | 1 |
| 1 | Scaffold & environment | Repo, venv, pinned deps, `/health` | 1 |
| 2 | Data | Loaders, common schema, demo sample | 1–2 |
| 3 | Aspect extraction | 3 switchable extractors + filter | 2 |
| 4 | Aspect grouping | Canonical aspects via WordNet + embeddings + seed lexicon | 3 |
| 5 | Opinions & sentiment | Clause-scoped opinions, 3 scorers | 3–4 |
| 6 | Aggregation & storage | SQLite + per-product stats | 4 |
| 7 | API | All REST endpoints + tests | 4 |
| 8 | Frontend | 5 pages | 5 |
| 9 | Evaluation | One-command eval, ablations, error analysis | 5 |
| 10 | Tests & quality | Full pytest, lint/format, types | 5 |
| 11 | Docker & deploy | Live HF Space | 6 |
| 12 | Documentation | README, presentation outline, demo script | 6 |

*Matches the suggested six-week timeline.

---
## Phase 0 — Plan & approval
**Do:** Read BRAIN.md + all docs. Produce an implementation plan and task list. Verify dataset/model availability (SemEval-2014, Amazon Reviews, spaCy model, HF models). Propose fallbacks.
**Exit:** Human approves plan. Availability report written.

## Phase 1 — Scaffold & environment
**Do:** Create repo structure (see ARCHITECTURE.md), venv, `requirements.txt` (pinned), `.gitignore`, `.dockerignore`, minimal FastAPI app with `GET /health`.
**Exit:** `uvicorn app.main:app` starts; `/health` returns OK; deps install cleanly on Python 3.11.

## Phase 2 — Data
**Do:** Scripts to obtain (a) SemEval-2014 Task 4 laptop + restaurant data, (b) Amazon reviews sample, ~10–20 products, 20k–50k reviews. Parse to common schema `(review_id, product_id, text, rating, date)`. Create demo sample (a few thousand reviews, **< 20 MB**) and commit it. Do not commit full datasets.
**Exit:** Loaders run; basic stats print (counts, rating distribution, avg length, products).

## Phase 3 — Aspect extraction
**Do:** `nlp/preprocess.py` + `nlp/aspects.py`. Three extractors, each switchable: (1) NLTK RegexpParser, (2) spaCy noun chunks, (3) dependency rules (subject + adjective complement; adjective modifier + noun). Lemmatize, drop generic nouns, keep frequent candidates per product.
**Exit:** Unit tests pass on ≥ **15** hand-written sentences; each method toggleable via config.

## Phase 4 — Aspect grouping
**Do:** `nlp/grouping.py`. WordNet synonyms + MiniLM cosine similarity with agglomerative clustering + seed lexicon (battery, price, delivery, display, camera, performance, build quality, customer service, packaging, sound, software). Seed lexicon is a configurable JSON.
**Exit:** Clustering output for demo products printed for manual review; lexicon editable without code changes.

## Phase 5 — Opinions & sentiment
**Do:** `nlp/opinions.py` + `nlp/sentiment.py` + `nlp/pipeline.py`. Dependency-first opinion linking, ≤5-token same-clause fallback, clause split on contrast words, negation + intensifiers. Scorers: VADER, pretrained transformer, optional fine-tuned (sentence + aspect pair), all behind one interface returning `label, confidence, opinion_words`.
**Exit:** Example review returns **battery→positive, delivery→negative, price→negative** with correct opinion words and correct char offsets.

## Phase 6 — Aggregation & storage
**Do:** `app/db.py` + `nlp/aggregate.py`. Persist reviews + aspect mentions (see DATABASE_SCHEMA.md). Compute per product/aspect: mentions, pos %, neg %, avg score, monthly trend, top-3 pos + top-3 neg snippets.
**Exit:** Summary queries covered by tests.

## Phase 7 — API
**Do:** `GET /health`, `POST /analyze`, `POST /analyze/batch`, `POST /upload`, `GET /products`, `GET /products/{id}/summary`, `GET /compare?a=&b=`, `GET /evaluation`. Validation, text-length + batch-size caps, rate limiting, JSON errors, models loaded at startup, CORS only as needed.
**Exit:** API tests pass; `/docs` works.

## Phase 8 — Frontend
**Do:** Five tabs per DESIGN_SYSTEM.md: Analyze, Product Dashboard, Compare, Evaluation, About. Responsive, accessible, loading + error states.
**Exit:** Every page works against the running API; keyboard navigable; contrast passes.

## Phase 9 — Evaluation
**Do:** Scripts that compute and save to `eval/results/` (JSON + CSV):
- Extraction P/R/F1 on SemEval per ablation: chunks only → + dependency rules → + frequency filter → + grouping
- Aspect sentiment accuracy + macro-F1: VADER vs transformer vs (optional) fine-tuned, **identical splits**
- TF-IDF + logistic regression whole-review baseline
- Amazon: % of 4–5★ reviews with ≥1 negative aspect; % of 1–2★ with ≥1 positive aspect
- Avg latency / review
- Error analysis: ≥ **50** misclassified examples with category (implicit aspect, negation, sarcasm, multi-aspect clause, comparison, other)
**Exit:** One command (`python -m eval.run_all`) regenerates every file the Evaluation page and README read.

## Phase 10 — Tests & quality
**Do:** pytest across preprocessing, extraction, grouping, opinions, scorers (mock heavy models), API. Type hints, docstrings, formatter + linter config.
**Exit:** Tests pass from a clean checkout.

## Phase 11 — Docker & deployment
**Do:** Dockerfile (`python:3.11-slim`; install deps; download spaCy model, NLTK data, HF models **at build time**; non-root user; port 7860). HF Space README front matter `sdk: docker`, `app_port: 7860`. **Ask before** pushing to GitHub / creating the Space. Test every page + endpoint on the live URL.
**Exit:** Public URL works; live `/analyze` returns correct output for the example review.

## Phase 12 — Documentation
**Do:** README (problem, features, Mermaid architecture, pipeline ↔ syllabus units, setup/run, API reference with examples, **real** eval results, limitations, ethics, live demo link, cold-start note). `docs/presentation_outline.md` (slide-by-slide + 3-min demo script). Midterm package + viva Q&A notes.
**Exit:** README numbers match eval files exactly; final report delivered.

---
## Academic deliverables checklist
**Midterm (5):** problem statement · objectives · scope/out-of-scope · dataset choice · architecture diagram · pipeline description · evaluation plan · team roles · timeline
**Final (5):** hosted demo · eval w/ ablations + error analysis · short presentation · live walkthrough

## Stretch goals (only after Phase 12)
Fine-tuned BERT aspect-pair classifier (Colab notebook) · multi-domain lexicons · CSV export of results · aspect-term suggestions for unseen domains

## Scope guardrails (out of scope)
User accounts/login · payments · scraping live sites · multilingual reviews · real-time streaming · mobile app
