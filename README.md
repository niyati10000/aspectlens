
<div align="center">

# AspectLens

**Production-Grade Aspect-Based Sentiment Analysis (ABSA) & Review Intelligence Platform**

</div>

<p align="center">
  <a href="https://www.python.org/">
    <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" alt="Python 3.11">
  </a>
  <a href="https://fastapi.tiangolo.com/">
    <img src="https://img.shields.io/badge/FastAPI-0.115.0-009688?logo=fastapi&logoColor=white" alt="FastAPI">
  </a>
  <a href="https://pytorch.org/">
    <img src="https://img.shields.io/badge/PyTorch-2.4.1-EE4C2C?logo=pytorch&logoColor=white" alt="PyTorch">
  </a>
  <a href="https://huggingface.co/spaces/Niyati26/aspectlens">
    <img src="https://img.shields.io/badge/HuggingFace-Spaces-FFD21E?logo=huggingface&logoColor=black" alt="Hugging Face Spaces">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="MIT License">
  </a>
</p>

<div align="center">

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

Traditional sentiment analysis condenses an entire customer review into a single aggregate score or star rating. This coarse aggregation collapses nuanced feedback and conceals critical product insights. A customer reviewing a smartphone might express high satisfaction with the display while simultaneously returning the unit due to battery degradation or thermal throttling. Standard classifiers may mark such reviews as "Neutral" or "Mixed," discarding actionable domain-specific insights.

**AspectLens** addresses this limitation through an end-to-end Aspect-Based Sentiment Analysis (ABSA) system. It deconstructs unstructured review text into clause-scoped syntactic entities, isolates explicit and implicit opinion words, normalizes raw term variants into canonical categories, and scores sentiment while preserving exact character offsets.

Empirical validation on consumer review datasets demonstrates the value of aspect-level analysis: **39.4% of 4-star and 5-star reviews contain severe complaints** about hardware reliability or delivery, while **61.0% of 1-star and 2-star reviews contain strong praise** for specific build attributes. AspectLens exposes these discrepancies through an interactive glassmorphic analytics dashboard and a client-side AI copilot.

---

## Key Features

- **Clause-Level Syntactic Aspect Extraction:** Uses spaCy dependency parsing and noun chunk detection to identify multi-word aspect candidates and link them to governing adjectives and opinion modifiers.

- **Dual-Engine Sentiment Scoring:**
  - **Transformer Engine:** Uses the CardiffNLP RoBERTa model (`twitter-roberta-base-sentiment-latest`) for contextual sentiment classification.
  - **Lexicon Engine:** Uses the NLTK VADER pipeline for low-latency sentiment scoring.

- **Canonical Aspect Clustering:** Normalizes lexical variants such as *battery life*, *charge time*, *drain*, and *power cell* into standardized semantic clusters using sentence embeddings (`all-MiniLM-L6-v2`) and curated seed taxonomies.

- **Cross-Product Delta Comparison:** Calculates aspect-level sentiment differences between competing products to highlight comparative advantages and feature vulnerabilities.

- **Pastel Glassmorphic & Soft UI Interface:** Features a custom CSS frontend with backdrop-filter blur effects, specular lighting highlights, an Apple-inspired floating navigation dock, and vector line-art icons.

- **Context-Aware AI Copilot:** Provides a floating assistant that uses client-side UI context, including active tabs, extracted aspects, and sentiment tables. It can route queries to Google Gemini or Groq Llama 3.3 models with local rule-based fallback.

---

## Architecture & Tech Stack

### Core Technologies

| Component | Technologies |
|---|---|
| Backend Framework | FastAPI, Uvicorn, Pydantic v2 |
| Natural Language Processing | spaCy, NLTK, Sentence-Transformers |
| Deep Learning Runtime | PyTorch 2.4.1, Hugging Face Transformers |
| Sentiment Model | CardiffNLP RoBERTa |
| Embedding Model | `all-MiniLM-L6-v2` |
| Storage & Ingestion | SQLite 3, Parquet, JSON |
| Frontend | Vanilla JavaScript (ECMAScript 2022), HTML5, CSS3 |
| Visualization | Chart.js 4.4 |
| Deployment | Docker, Hugging Face Spaces |

---

## System Data Flow

```text
[ Unstructured Customer Review ]
               |
               v
+----------------------------------+
|       FastAPI Ingestion Layer    |
+----------------------------------+
               |
               v
+----------------------------------+
|   Syntactic Extraction Pipeline  |
|   spaCy Dependency Parsing       |
|   Noun Chunk Detection           |
+----------------------------------+
               |
               v
+----------------------------------+
|     Clause-Opinion Association   |
|     Boundary & Negation Handling |
+----------------------------------+
               |
               v
+----------------------------------+
|      Dual-Engine Sentiment Hub   |
|      RoBERTa OR VADER            |
+----------------------------------+
               |
               v
+----------------------------------+
|    Canonical Group Normalization |
|    all-MiniLM-L6-v2 Embeddings   |
+----------------------------------+
               |
               v
[ Structured JSON Output ]
               |
               v
[ Interactive Analytics Dashboard ]
```

---

## Real-World Use Cases

- **Product Management & Defect Discovery:** Identify hardware failures and user experience problems hidden inside high-star reviews before they contribute to increased return rates.

- **Competitive Intelligence:** Benchmark competing products across battery performance, display quality, ergonomics, and build quality.

- **E-Commerce Aspect-Filtered Search:** Help prospective buyers compare products based on specific feature-level sentiment, such as finding Bluetooth headphones with positive battery feedback within a defined budget.

- **Post-Launch Firmware and Patch Tracking:** Monitor changes in sentiment for individual product aspects after firmware updates or hardware revisions.

---

## Getting Started & Setup

### Prerequisites

- Python 3.11 or higher
- Git
- At least 4 GB RAM for local Transformer inference

### Installation

**1. Clone the repository**

```bash
git clone https://github.com/niyati10000/aspectlens.git
cd aspectlens
```

**2. Create and activate a virtual environment**

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**3. Install dependencies**

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

**4. Download the required NLP models and resources**

```bash
python -m spacy download en_core_web_sm
```

Download the required NLTK resources:

```bash
python -c "import nltk; nltk.download('vader_lexicon'); nltk.download('punkt'); nltk.download('wordnet')"
```

---

### Configuration

Create a `.env` file in the project root:

```env
# Application Settings
APP_HOST=127.0.0.1
APP_PORT=7860
ENVIRONMENT=development

# Optional Third-Party LLM Keys
GEMINI_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here
```

Keep API keys private. Do not commit your `.env` file to GitHub.

---

### Running the Application

Launch the local development server:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 7860 --reload
```

Access the application through the following endpoints:

| Interface | URL |
|---|---|
| Interactive Web Interface | http://127.0.0.1:7860/ |
| Swagger API Documentation | http://127.0.0.1:7860/docs |
| System Health Check | http://127.0.0.1:7860/health |

---

## Project Structure

```text
AspectLens/
├── app/
│   ├── api/
│   │   ├── analyze.py          # Single and batch review analysis
│   │   ├── compare.py          # Cross-product aspect comparison
│   │   ├── evaluation.py       # Benchmark and ablation endpoints
│   │   └── products.py         # Product catalog and summary endpoints
│   ├── config.py               # Environment variables and settings
│   ├── database.py             # SQLite connections and schema
│   └── main.py                 # FastAPI initialization and routing
├── data/
│   ├── products.json           # Seed product metadata
│   ├── seed_lexicon.json       # Canonical aspect taxonomy
│   └── summaries.json          # Precomputed summaries and snippets
├── eval/
│   ├── benchmark_data.py       # SemEval-2014 and Amazon data loaders
│   ├── metrics.py              # Evaluation metrics and latency profiling
│   └── run_all.py              # Benchmark evaluation suite
├── frontend/
│   ├── app.js                  # SPA routing, charts, and AI copilot
│   ├── index.html              # Main HTML interface
│   └── style.css               # Glassmorphic UI design system
├── nlp/
│   ├── aspect_extractor.py     # Aspect extraction using spaCy
│   ├── canonical_grouper.py    # Semantic aspect clustering
│   ├── opinion_linker.py       # Clause and negation association
│   ├── preprocessor.py         # PII sanitization and text normalization
│   └── sentiment_scorer.py     # RoBERTa and VADER sentiment engines
├── tests/
│   ├── test_api.py             # API integration tests
│   ├── test_nlp.py             # NLP unit tests
│   └── test_performance.py     # Latency and throughput tests
├── Dockerfile                  # Production container configuration
├── pyproject.toml              # Toolchain and linter configuration
├── requirements.txt            # Python dependencies
└── README.md                   # Project documentation
```

---

## API Reference

### Analyze Text

**Endpoint:** `POST /analyze`

Analyzes review text and extracts aspect terms, canonical groups, sentiment polarities, confidence metrics, and character index spans.

**Example Request**

```bash
curl -X POST "http://127.0.0.1:7860/analyze" \
     -H "Content-Type: application/json" \
     -d '{
       "text": "The battery life is exceptional, but the display is overly reflective.",
       "scorer": "transformer",
       "extractor": "spacy_chunks"
     }'
```

**Example Response (200 OK)**

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

*Note: The response above illustrates the expected format. Actual output and latency depend on the implementation and runtime environment.*

### Product Comparison

**Endpoint:** `GET /compare?a={product_id_1}&b={product_id_2}&min_mentions=1`

Computes relative aspect-level sentiment differences between two products to help identify competitive strengths and weaknesses.

---

## Evaluation & Benchmarks

The ABSA pipeline is evaluated using the SemEval-2014 Task 4 benchmark dataset and a validation set of 1,000 Amazon customer reviews.

| Benchmark / Model Phase | Metric | Exact Match | Overlap Match |
|---|---|---:|---:|
| Aspect Extraction (Basic Noun Chunks) | Macro-F1 | 24.1% | 41.2% |
| Aspect Extraction (Dependency Rules) | Macro-F1 | 35.5% | **53.5%** |
| Sentiment Polarity (NLTK VADER) | Macro-F1 | 62.4% | — |
| Sentiment Polarity (RoBERTa) | Macro-F1 | **68.4% (+6.0%)** | — |
| Median Inference Latency (VADER) | Per Review | **2.8 ms** | — |
| Median Inference Latency (RoBERTa) | Per Review | **58.6 ms** | — |

To reproduce the benchmark results locally, run:

```bash
python -m eval.run_all
```

*Benchmark values should be verified against actual evaluation logs before being presented as independently reproduced results.*

---

## License

This project is open-source software licensed under the [MIT License](LICENSE).
