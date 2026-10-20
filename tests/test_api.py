"""Unit and integration tests for AspectLens FastAPI endpoints."""

import io

import pytest
from starlette.testclient import TestClient

from app.config import settings
from app.db import init_db
from app.limiter import limiter
from app.main import app


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Reset rate limiter before each test so limits do not collide across test cases."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(scope="module")
def client():
    """Test client with application lifespan and in-memory test database."""
    # Ensure database is initialized
    init_db(seed_if_empty=True)
    with TestClient(app) as c:
        yield c


# ----------------------------------------------------------------------
# 1. System Health & Docs
# ----------------------------------------------------------------------
def test_health_endpoint(client):
    """GET /health returns 200 with ok status and version."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == settings.APP_VERSION
    assert "models_loaded" in data


def test_docs_endpoint(client):
    """GET /docs returns 200 Swagger documentation."""
    response = client.get("/docs")
    assert response.status_code == 200
    assert (
        "swagger" in response.text.lower()
        or "openapi" in response.text.lower()
        or "html" in response.text.lower()
    )


def test_frontend_root_serving(client):
    """GET / serves index.html."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")


def test_security_headers(client):
    """All responses must include defense-in-depth security headers."""
    response = client.get("/health")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "no-referrer"
    assert "Content-Security-Policy" in response.headers


# ----------------------------------------------------------------------
# 2. Single Review Analysis: POST /analyze
# ----------------------------------------------------------------------
def test_analyze_golden_review(client):
    """POST /analyze with golden review returns expected structured aspects and offsets."""
    payload = {
        "text": "Battery life is amazing, but the delivery was late and the price is too high.",
        "scorer": "vader",
        "extractor": "spacy_chunks",
    }
    response = client.post("/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["text"] == payload["text"]
    assert data["scorer"] == "vader"
    assert "latency_ms" in data
    assert len(data["aspects"]) == 3

    aspects = {a["canonical"]: a for a in data["aspects"]}
    assert "Battery" in aspects
    assert aspects["Battery"]["sentiment"] == "positive"
    assert aspects["Battery"]["start"] == 0
    assert aspects["Battery"]["end"] == 12

    assert "Delivery" in aspects
    assert aspects["Delivery"]["sentiment"] == "negative"

    assert "Price" in aspects
    assert aspects["Price"]["sentiment"] == "negative"


def test_analyze_validation_errors(client):
    """POST /analyze validation: empty text, text too long, and unknown scorer."""
    # 1. Empty text
    res = client.post("/analyze", json={"text": ""})
    assert res.status_code == 422
    data = res.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"

    # 2. Text exceeds max review length
    long_text = "word " * (settings.MAX_REVIEW_LENGTH + 10)
    res_long = client.post("/analyze", json={"text": long_text})
    assert res_long.status_code in (413, 422)
    assert "error" in res_long.json()

    # 3. Invalid scorer
    res_scorer = client.post("/analyze", json={"text": "Good screen", "scorer": "invalid_scorer"})
    assert res_scorer.status_code == 422
    assert res_scorer.json()["error"]["code"] == "VALIDATION_ERROR"


# ----------------------------------------------------------------------
# 3. Batch Analysis: POST /analyze/batch
# ----------------------------------------------------------------------
def test_analyze_batch_endpoint(client):
    """POST /analyze/batch processes multiple reviews and returns aggregate stats."""
    payload = {
        "reviews": [
            "Great battery life and clear screen.",
            "Delivery was slow, but price was affordable.",
        ],
        "scorer": "vader",
        "extractor": "spacy_chunks",
    }
    response = client.post("/analyze/batch", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["total_reviews"] == 2
    assert len(data["results"]) == 2
    assert data["total_aspects"] >= 2
    assert "latency_ms" in data


def test_analyze_batch_limits(client):
    """POST /analyze/batch rejects batches exceeding MAX_BATCH_SIZE."""
    too_many_reviews = ["Great phone."] * (settings.MAX_BATCH_SIZE + 5)
    response = client.post("/analyze/batch", json={"reviews": too_many_reviews})
    assert response.status_code in (413, 422)
    assert "error" in response.json()


# ----------------------------------------------------------------------
# 4. Products Listing & Summary
# ----------------------------------------------------------------------
def test_list_products(client):
    """GET /products returns list of seeded demo products."""
    response = client.get("/products")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "id" in data[0]
    assert "name" in data[0]
    assert "review_count" in data[0]


def test_product_summary_and_not_found(client):
    """GET /products/{id}/summary returns product summary or 404 for unknown product."""
    # Fetch first product ID from list
    prods = client.get("/products").json()
    first_pid = prods[0]["id"]

    res = client.get(f"/products/{first_pid}/summary")
    assert res.status_code == 200
    summary = res.json()
    assert summary["product_id"] == first_pid
    assert "aspects" in summary
    assert "monthly_trend" in summary

    # 404 for non-existent product
    res_404 = client.get("/products/NON_EXISTENT_ID_9999/summary")
    assert res_404.status_code == 404
    data_404 = res_404.json()
    assert "error" in data_404
    assert data_404["error"]["code"] == "PRODUCT_NOT_FOUND"


# ----------------------------------------------------------------------
# 5. Product Comparison: GET /compare
# ----------------------------------------------------------------------
def test_compare_products_endpoint(client):
    """GET /compare returns side-by-side comparison for two valid products."""
    prods = client.get("/products").json()
    if len(prods) >= 2:
        pid_a = prods[0]["id"]
        pid_b = prods[1]["id"]

        res = client.get(f"/compare?a={pid_a}&b={pid_b}")
        assert res.status_code == 200
        data = res.json()
        assert "product_a" in data
        assert "product_b" in data
        assert "aspects" in data

    # 404 when comparing non-existent product
    res_bad = client.get("/compare?a=FAKE_A&b=FAKE_B")
    assert res_bad.status_code == 404
    assert res_bad.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


# ----------------------------------------------------------------------
# 6. CSV Upload: POST /upload
# ----------------------------------------------------------------------
def test_upload_csv_success(client):
    """POST /upload parses and ingests valid CSV data."""
    csv_content = (
        "product_id,text,rating,date\n"
        "UPLOAD_TEST_1,Battery life is fantastic and durable,5,2024-05-01\n"
        "UPLOAD_TEST_1,Terrible screen and poor sound quality,1,2024-05-02\n"
        "UPLOAD_TEST_2,Affordable price and fast delivery,4,2024-05-03\n"
    )
    file_bytes = io.BytesIO(csv_content.encode("utf-8"))
    response = client.post(
        "/upload",
        files={"file": ("test_upload.csv", file_bytes, "text/csv")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert data["rows_imported"] == 3
    assert data["products_count"] == 2


def test_upload_admin_key_enforcement(client, monkeypatch):
    """POST /upload enforces ADMIN_API_KEY when configured."""
    monkeypatch.setattr(settings, "ADMIN_API_KEY", "secret-admin-token")

    csv_content = "text\nGreat phone."
    file_bytes = io.BytesIO(csv_content.encode("utf-8"))

    # Missing key -> 401
    res_no_key = client.post(
        "/upload",
        files={"file": ("data.csv", file_bytes, "text/csv")},
    )
    assert res_no_key.status_code == 401
    assert res_no_key.json()["error"]["code"] == "UNAUTHORIZED"

    # Wrong key -> 401
    file_bytes.seek(0)
    res_wrong_key = client.post(
        "/upload",
        files={"file": ("data.csv", file_bytes, "text/csv")},
        headers={"X-API-Key": "wrong-token"},
    )
    assert res_wrong_key.status_code == 401

    # Valid key -> 200
    file_bytes.seek(0)
    res_valid = client.post(
        "/upload",
        files={"file": ("data.csv", file_bytes, "text/csv")},
        headers={"X-API-Key": "secret-admin-token"},
    )
    assert res_valid.status_code == 200


def test_upload_size_limit(client):
    """POST /upload rejects files exceeding MAX_CSV_SIZE_BYTES."""
    big_content = "a" * (settings.MAX_CSV_SIZE_BYTES + 50)
    file_bytes = io.BytesIO(big_content.encode("utf-8"))
    response = client.post(
        "/upload",
        files={"file": ("big.csv", file_bytes, "text/csv")},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"


def test_rate_limiting_trigger_429(client):
    """Verify that exceeding rate limits returns 429 with Retry-After header and clean error JSON."""
    csv_content = "text\nTest review."
    # Exhaust rate limit of 3/minute for /upload
    for _ in range(3):
        file_bytes = io.BytesIO(csv_content.encode("utf-8"))
        res = client.post("/upload", files={"file": ("limit.csv", file_bytes, "text/csv")})
        assert res.status_code == 200

    # 4th request must trigger 429
    file_bytes = io.BytesIO(csv_content.encode("utf-8"))
    res_429 = client.post("/upload", files={"file": ("limit.csv", file_bytes, "text/csv")})
    assert res_429.status_code == 429
    assert res_429.headers.get("Retry-After") is not None
    data = res_429.json()
    assert "error" in data
    assert data["error"]["code"] == "RATE_LIMIT_EXCEEDED"


# ----------------------------------------------------------------------
# 7. Evaluation: GET /evaluation
# ----------------------------------------------------------------------
def test_evaluation_endpoint(client):
    """GET /evaluation returns not_generated_yet or benchmark results."""
    response = client.get("/evaluation")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "message" in data
    assert "results" in data
