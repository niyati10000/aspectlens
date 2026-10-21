---
title: aspectlens
emoji: 🔍
colorFrom: blue
colorTo: indigo
sdk: static
pinned: false
license: mit
---

# AspectLens — Aspect-Based Review Mining System

AspectLens is an aspect-based sentiment analysis and review mining application built for customer review analytics, comparing products across granular dimensions (battery, delivery, price, display, etc.).

# Hosted link
https://niyati26-aspectlens.static.hf.space

## Tech Stack
- **Backend:** Python 3.11, FastAPI, Uvicorn, Pydantic
- **NLP:** spaCy (`en_core_web_sm`), NLTK (RegexpParser, WordNet, VADER), sentence-transformers (`all-MiniLM-L6-v2`), Hugging Face Transformers (`cardiffnlp/twitter-roberta-base-sentiment-latest`)
- **Storage:** SQLite
- **Frontend:** Vanilla HTML/CSS/JS + Chart.js (No Node.js build step)
- **Deployment:** Docker on Hugging Face Spaces (Port 7860)

## Quickstart

```bash
# 1. Create virtual environment (Python 3.11)
py -3.11 -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows

# 2. Install pinned dependencies
pip install -r requirements.txt

# 3. Run FastAPI application
uvicorn app.main:app --port 7860 --reload
```

## Docker

```bash
# Build image
docker build -t aspectlens .

# Run container
docker run -p 7860:7860 aspectlens
```

## Health Check
Visit `http://localhost:7860/health` or `http://localhost:7860/docs`.
