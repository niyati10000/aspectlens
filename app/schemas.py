"""Pydantic schemas and request/response models for AspectLens API."""

from typing import Any

from pydantic import BaseModel, Field

from app.config import settings


# ----------------------------------------------------------------------
# 1. Error & Health Schemas
# ----------------------------------------------------------------------
class HealthResponse(BaseModel):
    """Health check response reporting service status and model readiness."""

    status: str = "ok"
    models_loaded: bool = False
    version: str = settings.APP_VERSION


class ErrorDetail(BaseModel):
    """Structured error detail model."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Standard structured error response model matching ARCHITECTURE.md."""

    error: ErrorDetail


# ----------------------------------------------------------------------
# 2. Analyze Schemas
# ----------------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    """Request model for single review analysis."""

    text: str = Field(
        ...,
        min_length=1,
        max_length=settings.MAX_REVIEW_LENGTH,
        description=f"Review text to analyze (max {settings.MAX_REVIEW_LENGTH} chars)",
    )
    scorer: str = Field(
        default=settings.DEFAULT_SCORER,
        pattern="^(vader|transformer|finetuned)$",
        description="Sentiment scorer: 'vader', 'transformer', or 'finetuned'",
    )
    extractor: str = Field(
        default=settings.DEFAULT_EXTRACTOR,
        pattern="^(nltk_regex|spacy_chunks|spacy_deps|all)$",
        description="Aspect candidate extractor method",
    )


class AspectMentionResponse(BaseModel):
    """Single aspect mention result with character offsets referencing clean text."""

    term: str
    canonical: str
    start: int
    end: int
    sentiment: str
    confidence: float
    opinion_words: list[str]


class AnalyzeResponse(BaseModel):
    """Response matching ARCHITECTURE.md Section 5 schema."""

    text: str
    scorer: str
    aspects: list[AspectMentionResponse]
    latency_ms: float


class BatchAnalyzeRequest(BaseModel):
    """Request model for batch review analysis."""

    reviews: list[str] = Field(
        ...,
        min_length=1,
        max_length=settings.MAX_BATCH_SIZE,
        description=f"List of review texts (1 to {settings.MAX_BATCH_SIZE} reviews)",
    )
    scorer: str = Field(
        default=settings.DEFAULT_SCORER,
        pattern="^(vader|transformer|finetuned)$",
    )
    extractor: str = Field(
        default=settings.DEFAULT_EXTRACTOR,
        pattern="^(nltk_regex|spacy_chunks|spacy_deps|all)$",
    )


class BatchAnalyzeResponse(BaseModel):
    """Response model for batch analysis."""

    results: list[AnalyzeResponse]
    total_reviews: int
    total_aspects: int
    latency_ms: float


# ----------------------------------------------------------------------
# 3. Product & Aggregation Schemas
# ----------------------------------------------------------------------
class ProductItemResponse(BaseModel):
    """Product summary item."""

    id: str
    name: str
    category: str | None = None
    source: str | None = None
    review_count: int = 0


class RepresentativeSnippet(BaseModel):
    """Representative review snippet supporting an aspect sentiment."""

    id: int
    term: str
    snippet: str
    confidence: float
    score: float
    opinion_words: list[str]
    review_id: str
    rating: int | None = None
    review_date: str | None = None


class SnippetCollection(BaseModel):
    """Collection of positive and negative snippets."""

    positive: list[RepresentativeSnippet]
    negative: list[RepresentativeSnippet]


class AspectSummaryItem(BaseModel):
    """Aggregated statistics for a single canonical aspect."""

    aspect: str
    canonical_id: int
    mentions: int
    pos_pct: float
    neg_pct: float
    neu_pct: float
    avg_score: float
    snippets: SnippetCollection | None = None


class MonthlyTrendItem(BaseModel):
    """Sentiment trend for a single calendar month."""

    month: str
    aspect: str
    canonical_id: int
    mentions: int
    pos_pct: float
    neg_pct: float
    avg_score: float


class ProductDetailResponse(BaseModel):
    """Complete product summary including aspect metrics and trends."""

    product_id: str
    name: str
    category: str | None = None
    source: str | None = None
    review_count: int
    aspects: list[AspectSummaryItem]
    monthly_trend: list[MonthlyTrendItem]


# ----------------------------------------------------------------------
# 4. Product Comparison Schemas
# ----------------------------------------------------------------------
class ComparedAspectStats(BaseModel):
    """Per-product metrics in a side-by-side comparison."""

    mentions: int
    pos_pct: float
    neg_pct: float
    neu_pct: float
    avg_score: float


class ComparedAspectItem(BaseModel):
    """Single aspect comparison row."""

    aspect: str
    canonical_id: int
    product_a: ComparedAspectStats
    product_b: ComparedAspectStats
    winner: str


class CompareProductsResponse(BaseModel):
    """Side-by-side product comparison response."""

    product_a: dict[str, Any]
    product_b: dict[str, Any]
    aspects: list[ComparedAspectItem]


# ----------------------------------------------------------------------
# 5. CSV Upload Schema
# ----------------------------------------------------------------------
class UploadResponse(BaseModel):
    """Response returned upon successful CSV upload and ingestion."""

    batch_id: int
    filename: str
    rows_imported: int
    products_count: int
    status: str = "done"


# ----------------------------------------------------------------------
# 6. Evaluation Schema
# ----------------------------------------------------------------------
class EvaluationResponse(BaseModel):
    """Response model for benchmark evaluation results."""

    status: str
    message: str
    results: list[dict[str, Any]] = []
