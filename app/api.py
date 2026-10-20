"""FastAPI routers and endpoint implementations for AspectLens."""

import asyncio
import csv
import io
import json
import logging
import secrets
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile

from app.config import settings
from app.db import get_connection
from app.limiter import limiter
from app.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    BatchAnalyzeRequest,
    BatchAnalyzeResponse,
    CompareProductsResponse,
    ErrorResponse,
    EvaluationResponse,
    ProductDetailResponse,
    ProductItemResponse,
    UploadResponse,
)
from nlp.aggregate import (
    compare_products as aggregate_compare_products,
)
from nlp.aggregate import (
    get_product_summary,
)
from nlp.pipeline import analyze_batch, analyze_review
from nlp.preprocess import clean_text

logger = logging.getLogger(__name__)

router = APIRouter()


# ----------------------------------------------------------------------
# 1. Single Review Analysis
# ----------------------------------------------------------------------
@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
    responses={
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
    tags=["Analysis"],
)
@limiter.limit(settings.RATE_LIMIT_ANALYZE)
async def analyze_endpoint(
    request: Request,
    payload: AnalyzeRequest,
) -> AnalyzeResponse:
    """Analyze a single review text for aspect candidates, canonical grouping, and sentiment."""
    # Check max review length
    if len(payload.text) > settings.MAX_REVIEW_LENGTH:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "TEXT_TOO_LONG",
                "message": f"Review text length ({len(payload.text)} chars) exceeds maximum allowed ({settings.MAX_REVIEW_LENGTH} chars).",
            },
        )

    # Protect CPU with heavy job semaphore
    semaphore: asyncio.Semaphore | None = getattr(request.app.state, "heavy_job_semaphore", None)
    if semaphore:
        async with semaphore:
            result = await asyncio.to_thread(
                analyze_review,
                payload.text,
                scorer=payload.scorer,
                extractor=payload.extractor,
            )
    else:
        result = await asyncio.to_thread(
            analyze_review,
            payload.text,
            scorer=payload.scorer,
            extractor=payload.extractor,
        )

    return AnalyzeResponse(**result)


# ----------------------------------------------------------------------
# 2. Batch Review Analysis
# ----------------------------------------------------------------------
@router.post(
    "/analyze/batch",
    response_model=BatchAnalyzeResponse,
    responses={
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
    tags=["Analysis"],
)
@limiter.limit(settings.RATE_LIMIT_BATCH)
async def analyze_batch_endpoint(
    request: Request,
    payload: BatchAnalyzeRequest,
) -> BatchAnalyzeResponse:
    """Analyze multiple review texts in a single batch (capped at MAX_BATCH_SIZE)."""
    if len(payload.reviews) > settings.MAX_BATCH_SIZE:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "BATCH_TOO_LARGE",
                "message": f"Batch size ({len(payload.reviews)}) exceeds maximum allowed ({settings.MAX_BATCH_SIZE} reviews).",
            },
        )

    for i, rev in enumerate(payload.reviews):
        if len(rev) > settings.MAX_REVIEW_LENGTH:
            raise HTTPException(
                status_code=413,
                detail={
                    "code": "TEXT_TOO_LONG",
                    "message": f"Review at index {i} exceeds maximum length of {settings.MAX_REVIEW_LENGTH} characters.",
                },
            )

    t_start = asyncio.get_event_loop().time()
    semaphore: asyncio.Semaphore | None = getattr(request.app.state, "heavy_job_semaphore", None)

    if semaphore:
        async with semaphore:
            batch_results = await asyncio.to_thread(
                analyze_batch,
                payload.reviews,
                scorer=payload.scorer,
                extractor=payload.extractor,
            )
    else:
        batch_results = await asyncio.to_thread(
            analyze_batch,
            payload.reviews,
            scorer=payload.scorer,
            extractor=payload.extractor,
        )

    duration_ms = round((asyncio.get_event_loop().time() - t_start) * 1000, 1)
    total_aspects = sum(len(r["aspects"]) for r in batch_results)

    return BatchAnalyzeResponse(
        results=[AnalyzeResponse(**r) for r in batch_results],
        total_reviews=len(payload.reviews),
        total_aspects=total_aspects,
        latency_ms=duration_ms,
    )


# ----------------------------------------------------------------------
# 3. CSV Dataset Upload
# ----------------------------------------------------------------------
@router.post(
    "/upload",
    response_model=UploadResponse,
    responses={
        401: {"model": ErrorResponse},
        413: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
    },
    tags=["Data"],
)
@limiter.limit(settings.RATE_LIMIT_UPLOAD)
async def upload_csv_endpoint(
    request: Request,
    file: UploadFile = File(...),
    text_col: str | None = Form(None),
    product_id_col: str | None = Form(None),
    rating_col: str | None = Form(None),
    date_col: str | None = Form(None),
) -> UploadResponse:
    """Upload and ingest a CSV file of product reviews with optional column mapping.

    Enforces file size cap (2 MB), row cap (2,000 rows), and optional ADMIN_API_KEY.
    """
    # 1. Admin API key verification (if configured)
    if settings.ADMIN_API_KEY:
        client_key = request.headers.get("X-API-Key")
        if not client_key or not secrets.compare_digest(client_key, settings.ADMIN_API_KEY):
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "UNAUTHORIZED",
                    "message": "Invalid or missing X-API-Key header.",
                },
            )

    # 2. Check file extension / content type
    filename = file.filename or "upload.csv"
    if not (
        filename.lower().endswith(".csv")
        or "csv" in (file.content_type or "").lower()
        or "text" in (file.content_type or "").lower()
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_FILE_TYPE",
                "message": "Uploaded file must be a valid CSV file.",
            },
        )

    # 3. Read content with size cap
    max_bytes = settings.MAX_CSV_SIZE_BYTES
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "FILE_TOO_LARGE",
                "message": f"CSV file exceeds maximum allowed size of {max_bytes} bytes (2 MB).",
            },
        )

    # 4. Decode content as UTF-8
    try:
        decoded_text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            decoded_text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "INVALID_ENCODING",
                    "message": "CSV file must be UTF-8 encoded.",
                },
            )

    # 5. Parse CSV rows safely
    try:
        reader = csv.DictReader(io.StringIO(decoded_text))
        rows = list(reader)
    except Exception as e:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CSV_PARSE_ERROR",
                "message": f"Failed to parse CSV: {str(e)}",
            },
        )

    if not rows:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "EMPTY_CSV",
                "message": "Uploaded CSV contains no rows.",
            },
        )

    if len(rows) > settings.MAX_CSV_ROWS:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "CSV_ROW_LIMIT_EXCEEDED",
                "message": f"CSV row count ({len(rows)}) exceeds maximum allowed ({settings.MAX_CSV_ROWS} rows).",
            },
        )

    headers = [h.strip() for h in (reader.fieldnames or []) if h]
    headers_lower = {h.lower(): h for h in headers}

    # Auto-detect text column
    actual_text_col = text_col
    if not actual_text_col:
        for candidate in ["text", "review", "review_text", "comment", "body", "content", "summary"]:
            if candidate in headers_lower:
                actual_text_col = headers_lower[candidate]
                break

    if not actual_text_col or actual_text_col not in headers:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "MISSING_TEXT_COLUMN",
                "message": f"Could not find a review text column in headers: {headers}. Please specify 'text_col'.",
            },
        )

    # Auto-detect product_id column
    actual_pid_col = product_id_col
    if not actual_pid_col:
        for candidate in ["product_id", "asin", "product", "item_id", "sku", "id"]:
            if candidate in headers_lower:
                actual_pid_col = headers_lower[candidate]
                break

    # Auto-detect rating column
    actual_rating_col = rating_col
    if not actual_rating_col:
        for candidate in ["rating", "stars", "score"]:
            if candidate in headers_lower:
                actual_rating_col = headers_lower[candidate]
                break

    # Auto-detect date column
    actual_date_col = date_col
    if not actual_date_col:
        for candidate in ["date", "review_date", "timestamp", "time"]:
            if candidate in headers_lower:
                actual_date_col = headers_lower[candidate]
                break

    # 6. Insert batch and rows into database
    conn = get_connection()
    now_iso = datetime.now(UTC).isoformat()
    default_pid = Path(filename).stem or "uploaded_product"

    products_seen = set()
    review_records = []

    with conn:
        # Create upload_batches record
        batch_cur = conn.execute(
            """
            INSERT INTO upload_batches (created_at, filename, row_count, status)
            VALUES (?, ?, ?, 'processing');
            """,
            (now_iso, filename, len(rows)),
        )
        batch_id: int = batch_cur.lastrowid or 0

        for idx, row in enumerate(rows, 1):
            raw_review_text = row.get(actual_text_col, "")
            cleaned = clean_text(raw_review_text)
            if not cleaned:
                continue

            # Product ID
            pid = (row.get(actual_pid_col) or default_pid).strip()
            if not pid:
                pid = default_pid
            products_seen.add(pid)

            # Rating
            rating_val = None
            if actual_rating_col and row.get(actual_rating_col):
                try:
                    rating_val = int(float(row[actual_rating_col]))
                except (ValueError, TypeError):
                    rating_val = None

            # Date
            rev_date = row.get(actual_date_col, "") if actual_date_col else None
            if rev_date:
                rev_date = rev_date.strip()[:10]  # Take YYYY-MM-DD prefix

            overall = "neutral"
            if rating_val is not None:
                if rating_val >= 4:
                    overall = "positive"
                elif rating_val <= 2:
                    overall = "negative"

            r_id = f"up_{batch_id}_{idx}"
            review_records.append(
                (
                    r_id,
                    pid,
                    batch_id,
                    cleaned,
                    rating_val,
                    rev_date,
                    overall,
                    None,  # processed_at
                )
            )

        # Insert products
        for pid in products_seen:
            conn.execute(
                """
                INSERT OR IGNORE INTO products (id, name, category, source, review_count)
                VALUES (?, ?, 'Uploaded', 'upload', 0);
                """,
                (pid, f"Product {pid}"),
            )

        # Insert reviews
        conn.executemany(
            """
            INSERT OR REPLACE INTO reviews (
                id, product_id, batch_id, text_display, rating, review_date, overall_label, processed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            review_records,
        )

        # Update batch status and product review counts
        conn.execute(
            "UPDATE upload_batches SET status = 'done', row_count = ? WHERE id = ?;",
            (len(review_records), batch_id),
        )
        for pid in products_seen:
            conn.execute(
                """
                UPDATE products
                SET review_count = (SELECT COUNT(*) FROM reviews WHERE product_id = ?)
                WHERE id = ?;
                """,
                (pid, pid),
            )

    return UploadResponse(
        batch_id=batch_id,
        filename=filename,
        rows_imported=len(review_records),
        products_count=len(products_seen),
        status="done",
    )


# ----------------------------------------------------------------------
# 4. Products Listing & Summary
# ----------------------------------------------------------------------
@router.get(
    "/products",
    response_model=list[ProductItemResponse],
    tags=["Products"],
)
async def list_products_endpoint() -> list[ProductItemResponse]:
    """Retrieve all available products and their review counts."""
    conn = get_connection()
    cursor = conn.execute(
        """
        SELECT id, name, category, source, review_count
        FROM products
        ORDER BY review_count DESC, name ASC;
        """
    )
    rows = cursor.fetchall()
    return [ProductItemResponse(**dict(r)) for r in rows]


@router.get(
    "/products/{product_id}/summary",
    response_model=ProductDetailResponse,
    responses={404: {"model": ErrorResponse}},
    tags=["Products"],
)
async def product_summary_endpoint(
    product_id: str,
    min_mentions: int = Query(default=1, ge=0, description="Minimum mentions threshold"),
) -> ProductDetailResponse:
    """Retrieve aggregated aspect statistics, monthly sentiment trends, and snippets for a product."""
    conn = get_connection()
    summary = get_product_summary(conn, product_id, min_mentions=min_mentions)
    if not summary:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PRODUCT_NOT_FOUND",
                "message": f"Product with id '{product_id}' was not found.",
            },
        )
    return ProductDetailResponse(**summary)


# ----------------------------------------------------------------------
# 5. Side-by-Side Product Comparison
# ----------------------------------------------------------------------
@router.get(
    "/compare",
    response_model=CompareProductsResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    tags=["Products"],
)
async def compare_products_endpoint(
    a: str = Query(..., description="First product ID"),
    b: str = Query(..., description="Second product ID"),
    min_mentions: int = Query(default=1, ge=0, description="Minimum mentions threshold"),
) -> CompareProductsResponse:
    """Perform a side-by-side aspect sentiment comparison between two products."""
    prod_a_id = a.strip()
    prod_b_id = b.strip()

    if not prod_a_id or not prod_b_id:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_PARAMS",
                "message": "Both 'a' and 'b' product IDs must be provided.",
            },
        )

    conn = get_connection()

    # Verify both products exist
    cur_a = conn.execute("SELECT id FROM products WHERE id = ?;", (prod_a_id,)).fetchone()
    if not cur_a:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PRODUCT_NOT_FOUND",
                "message": f"Product '{prod_a_id}' was not found.",
            },
        )

    cur_b = conn.execute("SELECT id FROM products WHERE id = ?;", (prod_b_id,)).fetchone()
    if not cur_b:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "PRODUCT_NOT_FOUND",
                "message": f"Product '{prod_b_id}' was not found.",
            },
        )

    comparison = aggregate_compare_products(conn, prod_a_id, prod_b_id, min_mentions=min_mentions)
    return CompareProductsResponse(**comparison)


# ----------------------------------------------------------------------
# 6. Evaluation Benchmark Results
# ----------------------------------------------------------------------
@router.get(
    "/evaluation",
    response_model=EvaluationResponse,
    tags=["Evaluation"],
)
async def get_evaluation_results_endpoint() -> EvaluationResponse:
    """Retrieve offline benchmark evaluation results from eval/results/."""
    results_dir = settings.EVAL_RESULTS_DIR

    if not results_dir.exists():
        return EvaluationResponse(
            status="not_generated_yet",
            message="Evaluation results have not been generated yet. Run 'python -m eval.run_all' to execute benchmarks.",
            results=[],
        )

    # Search for all result JSON files
    json_files = list(results_dir.glob("*.json"))
    if not json_files:
        return EvaluationResponse(
            status="not_generated_yet",
            message="Evaluation results have not been generated yet. Run 'python -m eval.run_all' to execute benchmarks.",
            results=[],
        )

    collected_results = []
    for jf in sorted(json_files):
        try:
            with open(jf, encoding="utf-8") as f:
                data = json.load(f)
                collected_results.append(
                    {
                        "benchmark": jf.stem,
                        "data": data,
                    }
                )
        except Exception as e:
            logger.warning("Could not read evaluation file %s: %s", jf, e)

    return EvaluationResponse(
        status="ok",
        message=f"Found {len(collected_results)} benchmark evaluation result files.",
        results=collected_results,
    )
