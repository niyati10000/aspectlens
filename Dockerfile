# Dockerfile for AspectLens on Hugging Face Spaces (Port 7860)
FROM python:3.11-slim

# System configuration and environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860 \
    HOME=/home/appuser \
    HF_HOME=/home/appuser/.cache/huggingface \
    TRANSFORMERS_CACHE=/home/appuser/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/home/appuser/.cache/sentence_transformers \
    NLTK_DATA=/home/appuser/nltk_data

# Install essential system dependencies and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user (Hugging Face Spaces uses UID 1000)
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install Python dependencies first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download spaCy model, NLTK corpora, and Hugging Face models at build time
RUN mkdir -p /home/appuser/nltk_data /home/appuser/.cache && \
    python -m spacy download en_core_web_sm && \
    python -m nltk.downloader -d /home/appuser/nltk_data vader_lexicon wordnet omw-1.4 punkt punkt_tab && \
    python -c "\
from sentence_transformers import SentenceTransformer; \
from transformers import AutoTokenizer, AutoModelForSequenceClassification; \
print('Pre-caching MiniLM embeddings...'); \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); \
print('Pre-caching RoBERTa sentiment...'); \
AutoTokenizer.from_pretrained('cardiffnlp/twitter-roberta-base-sentiment-latest'); \
AutoModelForSequenceClassification.from_pretrained('cardiffnlp/twitter-roberta-base-sentiment-latest'); \
print('Build-time model download complete.')"

# Copy application code
COPY . .

# Set ownership to non-root user
RUN chown -R appuser:appuser /app /home/appuser

USER appuser

EXPOSE 7860

# Run FastAPI app with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
