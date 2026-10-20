# BRAIN.md — AspectLens Context Anchor

> **READ THIS FIRST, EVERY SESSION.** Then read the file for the phase you are working on (see "File Map"). Update the **Status** block at the bottom before you stop.

## 1. One-line pitch
AspectLens reads customer reviews, finds **what people talk about** (battery, delivery, price, display…) and **how they feel about each thing**, then shows per-review, per-product and product-vs-product breakdowns in a hosted web app + REST API.

## 2. Why it exists
Whole-review sentiment and star ratings hide the detail. "Battery life is amazing, but the delivery was late and the price is too high" is just "mixed" to a normal model. AspectLens returns: battery → positive, delivery → negative, price → negative.

## 3. Context
- University **NLP mini project** (10 marks: 5 midterm = scope/objectives, 5 final = implementation + presentation).
- Priorities, in order: **honest evaluation > correct classic-NLP technique > code clarity > scale**.
- Must map to syllabus units: U2 preprocessing/TF-IDF/similarity, U3 regex/corpora, U4 POS/chunking/parsing, U5 WordNet/word2vec, U7 sentiment classification.
- Presented as a *combined system with a measured comparison of methods*, not a single-technique demo.

## 4. Core flow
```
Browser dashboard → FastAPI → NLP pipeline → SQLite
                                  │
  preprocess → POS + chunk → aspect candidates → filter → group
            → opinion association (clause-scoped) → sentiment scorer
                                  
Offline: eval/ scripts → SemEval benchmark → JSON/CSV results → shown on Evaluation page
```

## 5. Locked-in decisions (do NOT re-argue)
| Area | Decision |
|---|---|
| Language | Python 3.11 |
| Backend | FastAPI + Uvicorn + Pydantic |
| Storage | SQLite (SQLAlchemy or plain sqlite3) |
| NLP | spaCy `en_core_web_sm` (tokens, POS, noun chunks, deps); NLTK (RegexpParser, WordNet, lemmatizer); VADER |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` |
| Transformer sentiment | `cardiffnlp/twitter-roberta-base-sentiment-latest`; fallback `distilbert-base-uncased-finetuned-sst-2-english` |
| Frontend | Plain HTML/CSS/JS + Chart.js, served by FastAPI static files. **No Node build step.** |
| Hosting | Docker on Hugging Face Spaces (free CPU, port 7860); code on GitHub |
| Auth | **None.** No users table. Public read-only demo. (See SECURITY_AND_ACCESS.md) |
| Datasets | SemEval-2014 Task 4 (eval); Amazon Reviews sample (demo); Kaggle fallback |
| Chunk grammar | `NP: {<DT>?<JJ>*<NN.*>+}` |

## 6. Non-negotiable NLP rules
1. Never remove stopwords before POS tagging.
2. Lowercase only a **copy** for matching; keep original text + **character offsets** for highlighting.
3. Generic-noun blacklist: thing, product, item, one, time, day, way, lot, bit, stuff (+ similar).
4. Keep an aspect only if it appears in ≥ N reviews for that product (default **5**, configurable).
5. Opinion linking: dependency arcs first → fallback window ≤ 5 tokens **within the same clause** → never cross a contrast word (but, however, although, though, yet).
6. No opinion word found → return **neutral, low confidence**. Never guess.
7. Handle negation ("not good", "never arrived") and intensifiers explicitly.
8. Strip emails, phone numbers, reviewer names from displayed text.
9. Fix random seeds + data splits (reproducibility).

## 7. Non-negotiable engineering rules
- **Never invent results.** Every number in README / Evaluation page comes from running `eval/` scripts.
- Verify every dataset/model exists and downloads **before** depending on it; propose a fallback if not.
- Ask the human before: paid services, creating accounts, pushing to remotes.
- No secrets/tokens in code or repo. Repo < 100 MB; no full datasets or model weights committed.
- Load models **once** at startup; never per request.
- Structured JSON errors; never expose stack traces.
- Pin dependency versions after confirming they install together on Python 3.11.
- One git commit (or more) **per phase**, message prefixed `phase-N:`.

## 8. Glossary
| Term | Meaning |
|---|---|
| Aspect | A thing being talked about (e.g. "battery life") |
| Canonical aspect | Merged group name (e.g. **Battery**) |
| Opinion words | Words justifying a sentiment ("amazing", "late") |
| Clause | Sentence piece bounded by contrast words / punctuation |
| ABSA | Aspect-Based Sentiment Analysis |
| Scorer | One of: `vader`, `transformer`, `finetuned` (same interface) |
| Ablation | Re-running eval with one pipeline component added at a time |
| Seed lexicon | Hand-written canonical aspects + variants JSON per domain |

## 9. File map
| File | Read when |
|---|---|
| `BRAIN.md` | Always, first |
| `PLAN.md` | Choosing what to do next; checking exit criteria |
| `ARCHITECTURE.md` | Writing any code |
| `DATABASE_SCHEMA.md` | Touching storage or aggregation |
| `DESIGN_SYSTEM.md` | Touching `frontend/` |
| `SECURITY_AND_ACCESS.md` | Touching API limits, Docker, deployment |
| `PROMPTS.md` | Human copy-pastes the prompt for the current phase |

## 10. Placeholders the human must fill
- `{GITHUB_USERNAME}` · `{HF_USERNAME}` — never hard-code tokens; HF token goes in local env / Space secrets only.

## 11. Definition of done
1. Public HF Space URL works for every page + endpoint.
2. All tests pass; **one command** regenerates all evaluation outputs.
3. README numbers match generated eval files exactly.
4. Clear commit history by phase.
5. Final report: what was built, measured results, limitations, manual to-dos.

---
## STATUS (update every session)
- **Current phase:** 7 — API (completed)
- **Last completed phase:** 7 (API)
- **Last session summary:** Implemented FastAPI routes in app/api.py (GET /health, POST /analyze, POST /analyze/batch, POST /upload with CSV mapping & size/row limits, GET /products, GET /products/{id}/summary, GET /compare, GET /evaluation), app/limiter.py (per-IP rate limiting respecting X-Forwarded-For), app/main.py (lifespan model pre-warming, heavy job semaphore, global JSON exception handlers without stack traces, security headers middleware, CORS, static frontend mount at /), and tests/test_api.py (all 50 tests passing across entire repo).
- **Open questions / blockers:** None.
- **Next action:** Phase 8 (Frontend: Five-tab UI in plain HTML/CSS/JS + Chart.js connecting to the running API).
