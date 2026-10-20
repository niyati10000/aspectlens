# Dockerfile for AspectLens on Hugging Face Spaces (Port 7860)
FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download spaCy model and NLTK data during build
RUN python -m spacy download en_core_web_sm && \
    python -m nltk.downloader vader_lexicon wordnet omw-1.4 punkt

# Copy application source code
COPY . .

# Set permissions for non-root user
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
