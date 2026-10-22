```markdown
<div align="center">

# AspectLens

**Production-Grade Aspect-Based Sentiment Analysis (ABSA) & Review Intelligence Platform**

[![Python 3.11](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.4.1-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org/)
[![HuggingFace](https://img.shields.io/badge/HuggingFace-Spaces-FFD21E?logo=huggingface&logoColor=black)](https://huggingface.co/spaces/Niyati26/aspectlens)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[Live Demonstration](https://niyati26-aspectlens.static.hf.space) • [Hugging Face Space](https://huggingface.co/spaces/Niyati26/aspectlens) • [GitHub Repository](https://github.com/niyati10000/aspectlens)

</div>

---

## Table of Contents
- [Project Overview](#project-overview)
- [Key Features](#key-features)
- [Architecture & Tech Stack](#architecture--tech-stack)
- [System Data Flow](#system-data-flow)
- [Real-World Use Cases](#real-world-use-cases)
- [Getting Started & Setup](#getting-started--setup)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Configuration](#configuration)
  - [Running the Application](#running-the-application)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Evaluation & Benchmarks](#evaluation--benchmarks)
- [License](#license)

---

## Project Overview

Traditional sentiment analysis condenses an entire customer review into a single aggregate score or star rating. This coarse aggregation collapses nuanced feedback and conceals critical product insights. A customer reviewing a smartphone might express high satisfaction with the display while simultaneously returning the unit due to battery degradation or thermal throttling. Standard classifiers mark such reviews as "Neutral" or "Mixed," discarding the actionable domain specifics.

**AspectLens** addresses this blind spot through an end-to-end Aspect-Based Sentiment Analysis (ABSA) system. It deconstructs unstructured review text into clause-scoped syntactic entities, isolates explicit and implicit opinion words, normalizes raw term variants into canonical categories, and scores sentiment with exact character offsets.

Empirical validation on real consumer datasets demonstrates the commercial necessity of ABSA: **39.4% of 4-star and 5-star reviews contain severe complaints** about hardware reliability or delivery, while **61.0% of 1-star and 2-star reviews contain strong praise** for specific build attributes. AspectLens exposes these discrepancies through an interactive, glassmorphic analytics dashboard and a client-side AI copilot.

---

## Key Features

- **Clause-Level Syntactic Aspect Extraction:** Employs spaCy dependency parsing and noun chunk detection to identify multi-word aspect candidates and link them directly to their governing adjectives and opinion modifiers.
- **Dual-Engine Sentiment Scoring:**
  - *Transformer Engine:* Fine-tuned CardiffNLP RoBERTa model (`twitter-roberta-base-sentiment-latest`) for high-fidelity contextual polarity.
  - *Lexicon Engine:* High-throughput NLTK VADER pipeline optimized for low-latency batch processing.
- **Canonical Aspect Clustering:** Normalizes lexical variants (e.g., *"battery life"*, *"charge time"*, *"drain"*, *"power cell"*) into standardized semantic clusters using semantic similarity embeddings (`all-MiniLM-L6-v2`) and curated seed taxonomies.
- **Cross-Product Delta Comparison:** Computes aspect-by-aspect sentiment deltas between competing products, highlighting comparative advantages and feature vulnerabilities.
- **Pastel Glassmorphic & Soft UI Interface:** Pure CSS frontend featuring backdrop-filter blur physics, specular lighting edge highlights, an Apple-inspired floating navigation dock, and strict vector line-art iconography (zero unicode emojis).
- **Context-Aware AI Copilot:** Floating assistant that consumes client-side UI context (active tab, extracted aspects, sentiment tables) and routes queries to Google Gemini or Groq Llama 3.3 models with local rule-based failover.

---

## Architecture & Tech Stack

### Core Technologies
- **Backend Framework:** FastAPI, Uvicorn, Pydantic v2
- **Natural Language Processing:** spaCy (`en_core_web_sm`), NLTK (WordNet, VADER, RegexpParser), Sentence-Transformers (`all-MiniLM-L6-v2`)
- **Deep Learning Runtime:** PyTorch 2.4.1, Hugging Face Transformers (`cardiffnlp/twitter-roberta-base-sentiment-latest`)
- **Storage & Ingestion:** SQLite 3, Pre-computed Parquet/JSON summaries
- **Frontend Layer:** Vanilla ECMAScript 2022 (SPA hash routing), Chart.js 4.4, Native CSS Glassmorphism
- **Deployment:** Docker (multi-stage build), Hugging Face Spaces

---

## System Data Flow

```text
[ Unstructured Customer Review ]
               │
               ▼
┌───────────────────────────────┐
│     FastAPI Ingestion Layer    │ ───► Rate Limiter & Concurrency Semaphore
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│  Syntactic Extraction Pipeline │ ───► spaCy Dependency Parsing & Noun Chunks
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│   Clause-Opinion Association  │ ───► Syntactic Boundary & Negation Handling
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│   Dual-Engine Sentiment Hub   │ ───► RoBERTa (Transformer) OR VADER (Lexicon)
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│ Canonical Group Normalization │ ───► Cosine Similarity (all-MiniLM-L6-v2)
└──────────────┬────────────────┘
               │
               ▼
[ Structured JSON Output & Glassmorphic Analytics Presentation ]
```

---

## Real-World Use Cases

- **Product Management & Defect Discovery:** Identify critical hardware failures or UX friction points hidden inside high-star aggregate reviews before they escalate into high return rates.
- **Competitive Intelligence:** Perform side-by-side head-to-head benchmarking between flagship products to identify competitor weaknesses across battery, display, ergonomics, and build quality.
- **E-Commerce Aspect-Filtered Search:** Enable prospective buyers to filter product catalogs based on specific dimension polarities (e.g., *"Find Bluetooth headphones with positive battery ratings but under $100"*).
- **Post-Launch Firmware/Patch Tracking:** Monitor chronological sentiment shifts per aspect to measure customer response following firmware updates or hardware revisions.

---

## Getting Started & Setup

### Prerequisites
- Python 3.11 or higher
- Git
- 4 GB RAM minimum (for local Transformer model inference)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/niyati10000/aspectlens.git
   cd aspectlens
   ```

2. **Create and activate a virtual environment:**
   ```bash
   # Windows (PowerShell)
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1

   # Linux / macOS
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install project dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Download required language models:**
   ```bash
   python -m spacy download en_core_web_sm
   python -c "import nltk; nltk.download('vader_lexicon'); nltk.download('punkt'); nltk.download('wordnet')"
   ```

### Configuration

Create a `.env` file in the project root:

```env
# Application Settings
APP_HOST=127.0.0.1
APP_PORT=7860
ENVIRONMENT=development

# Optional Third-Party LLM Keys (Client Copilot uses browser localStorage by default)
GEMINI_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here
```

### Running the Application

Launch the local development server:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 7860 --reload
```

Access the interfaces:
- **Interactive Web Interface:** `http://127.0.0.1:7860/`
- **Interactive Swagger Documentation:** `http://127.0.0.1:7860/docs`
- **System Health Check:** `http://127.0.0.1:7860/health`

---

## Project Structure

```text
AspectLens/
├── app/
│   ├── api/
│   │   ├── analyze.py        # Single & batch review analysis endpoints
│   │   ├── compare.py        # Cross-product aspect delta comparison
│   │   ├── evaluation.py     # Benchmark results & ablation endpoints
│   │   └── products.py       # Catalog query & summary endpoints
│   ├── config.py             # App environment variables & settings
│   ├── database.py           # SQLite connection & schema models
│   └── main.py               # FastAPI application initialization & routing
├── data/
│   ├── products.json         # Seed product metadata
│   ├── seed_lexicon.json     # Canonical aspect grouping taxonomy
│   └── summaries.json        # Precomputed product aggregations & snippets
├── eval/
│   ├── benchmark_data.py     # SemEval-2014 Task 4 & Amazon loaders
│   ├── metrics.py            # Precision, Recall, Macro-F1, Latency profilers
│   └── run_all.py            # Reproducible benchmark evaluation suite
├── frontend/
│   ├── app.js                # SPA router, Chart.js controllers, AI copilot
│   ├── index.html            # Semantic HTML5 layout with floating glass dock
│   └── style.css             # Pastel glassmorphic & soft UI design system
├── nlp/
│   ├── aspect_extractor.py   # spaCy noun chunk & dependency rule extractor
│   ├── canonical_grouper.py  # Cosine clustering with sentence-transformers
│   ├── opinion_linker.py     # Syntactic clause & negation associator
│   ├── preprocessor.py       # PII sanitization & contraction expander
│   └── sentiment_scorer.py   # RoBERTa transformer & VADER lexicon engines
├── tests/
│   ├── test_api.py           # Endpoint integration tests
│   ├── test_nlp.py           # Extractor, linker, and scorer unit tests
│   └── test_performance.py   # Latency & throughput stress tests
├── Dockerfile                # Multi-stage production container configuration
├── pyproject.toml            # Project toolchain & linter configurations
├── requirements.txt          # Production Python dependencies
└── README.md                 # System documentation
```

---

## API Reference

### Analyze Text
`POST /analyze`

Analyzes review text and extracts aspect terms, canonical groups, sentiment polarities, confidence metrics, and character index spans.

```bash
curl -X POST "http://127.0.0.1:7860/analyze" \
     -H "Content-Type: application/json" \
     -d '{
       "text": "The battery life is exceptional, but the display is overly reflective.",
       "scorer": "transformer",
       "extractor": "spacy_chunks"
     }'
```

**Response (200 OK):**
```json
{
  "text": "The battery life is exceptional, but the display is overly reflective.",
  "scorer": "transformer",
  "aspects": [
    {
      "term": "battery life",
      "canonical": "Battery",
      "start": 4,
      "end": 16,
      "sentiment": "positive",
      "confidence": 0.982,
      "opinion_words": ["exceptional"]
    },
    {
      "term": "display",
      "canonical": "Display",
      "start": 41,
      "end": 48,
      "sentiment": "negative",
      "confidence": 0.894,
      "opinion_words": ["overly reflective"]
    }
  ],
  "latency_ms": 64.2
}
```

### Product Comparison
`GET /compare?a={product_id_1}&b={product_id_2}&min_mentions=1`

Computes relative aspect score differences between two products to determine competitive superiority.

---

## Evaluation & Benchmarks

The ABSA pipeline is evaluated across the SemEval-2014 Task 4 benchmark dataset and a validation set of 1,000 Amazon Customer Reviews:

| Benchmark / Model Phase | Metric | Exact Match | Overlap Match |
| :--- | :--- | :--- | :--- |
| **Aspect Extraction (Basic Noun Chunks)** | Macro-F1 | 24.1% | 41.2% |
| **Aspect Extraction (Dependency Rules)** | Macro-F1 | 35.5% | **53.5%** |
| **Sentiment Polarity (NLTK VADER Lexicon)** | Macro-F1 | 62.4% | — |
| **Sentiment Polarity (RoBERTa Transformer)**| Macro-F1 | **68.4%** (+6.0%) | — |
| **Median Inference Latency (VADER)** | Per Review | **2.8 ms** | — |
| **Median Inference Latency (RoBERTa)** | Per Review | **58.6 ms** | — |

To reproduce the benchmark figures locally:
```bash
python -m eval.run_all
```

---

## License

This project is open-source software licensed under the [MIT License](LICENSE).
```
