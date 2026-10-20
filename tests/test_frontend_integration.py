"""Frontend integration tests verifying all 5 pages against running API endpoints."""

import pytest
from starlette.testclient import TestClient

from app.db import init_db
from app.limiter import limiter
from app.main import app


@pytest.fixture(autouse=True)
def reset_limits():
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(scope="module")
def client():
    init_db(seed_if_empty=True)
    with TestClient(app) as c:
        yield c


def test_page_1_analyze_integration(client):
    """Page 1 (Analyze): submit review, receive aspect mentions and exact offsets."""
    text = "Battery life is amazing, but the delivery was late and the price is too high."
    res = client.post(
        "/analyze", json={"text": text, "scorer": "vader", "extractor": "spacy_chunks"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["text"] == text
    assert len(data["aspects"]) == 3

    # Check offsets
    for a in data["aspects"]:
        assert text[a["start"] : a["end"]] == a["term"]


def test_page_2_dashboard_integration(client):
    """Page 2 (Product Dashboard): fetch products, load summary, check aspects and snippets."""
    res_prods = client.get("/products")
    assert res_prods.status_code == 200
    products = res_prods.json()
    assert len(products) > 0

    first_pid = products[0]["id"]
    res_summary = client.get(f"/products/{first_pid}/summary?min_mentions=1")
    assert res_summary.status_code == 200
    summary = res_summary.json()
    assert summary["product_id"] == first_pid
    assert "review_count" in summary
    assert "aspects" in summary
    assert "monthly_trend" in summary

    # Check snippets structure
    for asp in summary["aspects"]:
        assert "snippets" in asp
        assert "positive" in asp["snippets"]
        assert "negative" in asp["snippets"]


def test_page_3_compare_integration(client):
    """Page 3 (Compare): side-by-side comparison for two products."""
    prods = client.get("/products").json()
    if len(prods) >= 2:
        pid_a = prods[0]["id"]
        pid_b = prods[1]["id"]
        res_comp = client.get(f"/compare?a={pid_a}&b={pid_b}&min_mentions=1")
        assert res_comp.status_code == 200
        comp = res_comp.json()
        assert "product_a" in comp
        assert "product_b" in comp
        assert "aspects" in comp
        for a in comp["aspects"]:
            assert "winner" in a
            assert "product_a" in a
            assert "product_b" in a


def test_page_4_evaluation_integration(client):
    """Page 4 (Evaluation): fetch evaluation state and populated benchmark results."""
    res_eval = client.get("/evaluation")
    assert res_eval.status_code == 200
    data = res_eval.json()
    assert data["status"] == "ok"
    assert len(data["results"]) == 7
    benchmarks = {r["benchmark"]: r["data"] for r in data["results"]}
    assert "summary_metrics" in benchmarks
    assert "extraction_ablation" in benchmarks
    assert "sentiment_benchmark" in benchmarks
    assert "baseline_comparison" in benchmarks
    assert "amazon_mixed_sentiment" in benchmarks
    assert "latency_benchmark" in benchmarks
    assert "error_analysis" in benchmarks


def test_page_5_static_assets_and_html(client):
    """Page 5 (About / HTML): check HTML structure, headers, and syllabus cards."""
    res_html = client.get("/")
    assert res_html.status_code == 200
    html = res_html.text

    # Check navigation tabs
    assert "#/analyze" in html
    assert "#/dashboard" in html
    assert "#/compare" in html
    assert "#/evaluation" in html
    assert "#/about" in html

    # Check 5 page sections
    assert 'id="page-analyze"' in html
    assert 'id="page-dashboard"' in html
    assert 'id="page-compare"' in html
    assert 'id="page-evaluation"' in html
    assert 'id="page-about"' in html

    # Check syllabus units on About page
    assert "Unit 1 · Text Normalization" in html
    assert "Unit 2 · Part-of-Speech Tagging" in html
    assert "Unit 3 · Distributional Semantics" in html
    assert "Unit 4 · Syntactic & Dependency Parsing" in html
    assert "Unit 5 · Sentiment Lexicons & Pretrained Transformers" in html
    assert "Unit 6 · Information Extraction & Aggregation" in html

    # Check Chart.js vendored script tag
    assert 'src="/static/chart.umd.min.js"' in html
    assert 'src="/static/app.js"' in html
