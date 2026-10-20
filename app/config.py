"""AspectLens configuration settings and constants."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings with environment variable override support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App metadata
    APP_NAME: str = "AspectLens"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 7860

    # Storage paths
    DATA_DIR: Path = BASE_DIR / "data"
    DB_PATH: Path = BASE_DIR / "data" / "aspectlens.db"
    SEED_LEXICON_PATH: Path = BASE_DIR / "data" / "seed_lexicon.json"
    DEMO_SAMPLE_PATH: Path = BASE_DIR / "data" / "demo_sample.json"
    EVAL_RESULTS_DIR: Path = BASE_DIR / "eval" / "results"

    # NLP defaults
    DEFAULT_SCORER: str = "vader"
    DEFAULT_EXTRACTOR: str = "spacy_chunks"
    MIN_ASPECT_FREQUENCY: int = 5
    CHUNK_GRAMMAR: str = r"NP: {<DT>?<JJ>*<NN.*>+}"
    SENTIMENT_MODEL: str = "cardiffnlp/twitter-roberta-base-sentiment-latest"
    SENTIMENT_FALLBACK_MODEL: str = "distilbert-base-uncased-finetuned-sst-2-english"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Input limits & abuse prevention
    MAX_REVIEW_LENGTH: int = 2000
    MAX_BATCH_SIZE: int = 50
    MAX_CSV_SIZE_BYTES: int = 2 * 1024 * 1024  # 2 MB
    MAX_CSV_ROWS: int = 2000

    # Rate limiting (requests per minute)
    RATE_LIMIT_ANALYZE: str = "30/minute"
    RATE_LIMIT_BATCH: str = "5/minute"
    RATE_LIMIT_UPLOAD: str = "3/minute"

    # Optional admin authentication
    ADMIN_API_KEY: str | None = None


settings = Settings()
