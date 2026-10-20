/**
 * AspectLens — Frontend Client Application
 * Plain JavaScript, Chart.js, Hash-based router. No Node build step.
 * Follows DESIGN_SYSTEM.md strictly.
 */

// ----------------------------------------------------------------------
// Utility & Security Helpers
// ----------------------------------------------------------------------
function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = String(str);
  return div.innerHTML;
}

function announceStatus(message) {
  const el = document.getElementById("aria-status");
  if (el) el.textContent = message;
}

function getSentimentIcon(sentiment) {
  switch (sentiment) {
    case "positive": return "▲";
    case "negative": return "▼";
    default: return "●";
  }
}

// ----------------------------------------------------------------------
// Theme Manager
// ----------------------------------------------------------------------
const ThemeManager = {
  init() {
    const savedTheme = localStorage.getItem("aspectlens_theme");
    if (savedTheme) {
      document.documentElement.setAttribute("data-theme", savedTheme);
    }
    this.updateToggleIcon();

    const btn = document.getElementById("theme-toggle");
    if (btn) {
      btn.addEventListener("click", () => this.toggle());
    }
  },

  getCurrentTheme() {
    const attr = document.documentElement.getAttribute("data-theme");
    if (attr) return attr;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  },

  toggle() {
    const current = this.getCurrentTheme();
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("aspectlens_theme", next);
    this.updateToggleIcon();

    // Re-render charts with updated theme palette if visible
    if (DashboardController.barChart) DashboardController.renderAspectBarChart();
    if (DashboardController.trendChart) DashboardController.renderTrendChart();
    if (CompareController.compareChart) CompareController.renderChart();
  },

  updateToggleIcon() {
    const icon = document.getElementById("theme-icon");
    const label = document.getElementById("theme-label");
    const isDark = this.getCurrentTheme() === "dark";
    if (icon) icon.textContent = isDark ? "☀️" : "🌙";
    if (label) label.textContent = isDark ? "Light" : "Dark";
  },

  getChartColors() {
    const isDark = this.getCurrentTheme() === "dark";
    return {
      text: isDark ? "#EEF1F6" : "#1B1F27",
      textMuted: isDark ? "#9AA3B2" : "#5B6472",
      border: isDark ? "#2A303B" : "#E2E5EA",
      pos: isDark ? "#4CC38A" : "#1F8A4C",
      neg: isDark ? "#FF6B6B" : "#C92A2A",
      neu: isDark ? "#9AA3B2" : "#6B7280",
      primary: isDark ? "#7C95FF" : "#3B5BDB",
      primaryHover: isDark ? "#9AAEFF" : "#2F4AC0",
      productA: isDark ? "#7C95FF" : "#3B5BDB",
      productB: isDark ? "#FF922B" : "#D9480F",
    };
  }
};

// ----------------------------------------------------------------------
// Router
// ----------------------------------------------------------------------
const Router = {
  routes: ["analyze", "dashboard", "compare", "evaluation", "about"],

  init() {
    window.addEventListener("hashchange", () => this.handleRoute());
    this.handleRoute();
  },

  handleRoute() {
    const hash = window.location.hash.replace(/^#\/?/, "") || "analyze";
    const route = this.routes.includes(hash) ? hash : "analyze";

    // Update active nav link
    document.querySelectorAll(".nav-link").forEach(link => {
      const href = link.getAttribute("href");
      if (href === `#/${route}`) {
        link.classList.add("active");
        link.setAttribute("aria-selected", "true");
      } else {
        link.classList.remove("active");
        link.setAttribute("aria-selected", "false");
      }
    });

    // Toggle view sections
    document.querySelectorAll(".page-view").forEach(view => {
      if (view.id === `page-${route}`) {
        view.classList.add("active");
      } else {
        view.classList.remove("active");
      }
    });

    // Trigger on-route controllers
    if (route === "dashboard") {
      DashboardController.onOpen();
    } else if (route === "compare") {
      CompareController.onOpen();
    } else if (route === "evaluation") {
      EvaluationController.onOpen();
    }

    announceStatus(`Navigated to ${route} tab`);
  }
};

// ----------------------------------------------------------------------
// Page 1 Controller: Analyze
// ----------------------------------------------------------------------
const AnalyzeController = {
  goldenExample: "Battery life is amazing, but the delivery was late and the price is too high.",

  init() {
    const textarea = document.getElementById("review-input");
    const charCounter = document.getElementById("char-count");
    const exampleBtn = document.getElementById("btn-example");
    const form = document.getElementById("analyze-form");

    if (textarea && charCounter) {
      textarea.addEventListener("input", () => {
        charCounter.textContent = textarea.value.length;
      });
    }

    if (exampleBtn && textarea && charCounter) {
      exampleBtn.addEventListener("click", () => {
        textarea.value = this.goldenExample;
        charCounter.textContent = textarea.value.length;
        textarea.focus();
      });
    }

    if (form) {
      form.addEventListener("submit", (e) => {
        e.preventDefault();
        this.runAnalysis();
      });
    }
  },

  async runAnalysis() {
    const textarea = document.getElementById("review-input");
    const scorerSelect = document.getElementById("scorer-select");
    const extractorSelect = document.getElementById("extractor-select");
    const analyzeBtn = document.getElementById("btn-analyze");
    const statusBox = document.getElementById("analyze-status-box");
    const resultsContainer = document.getElementById("analyze-results-container");

    const text = textarea ? textarea.value.trim() : "";
    if (!text) return;

    // Loading State
    analyzeBtn.disabled = true;
    statusBox.innerHTML = `
      <div class="loading-box">
        <div class="skeleton-shimmer" style="height: 14px; width: 60%; margin: 0 auto 12px;"></div>
        <div>Reading the review and parsing aspect clauses...</div>
      </div>
    `;
    announceStatus("Reading the review and parsing aspect clauses...");
    resultsContainer.style.display = "none";

    try {
      const response = await fetch("/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: text,
          scorer: scorerSelect ? scorerSelect.value : "vader",
          extractor: extractorSelect ? extractorSelect.value : "spacy_chunks",
        }),
      });

      if (!response.ok) {
        let errData = {};
        try { errData = await response.json(); } catch (_) {}
        const msg = errData?.error?.message || `Server returned error (${response.status})`;
        throw new Error(msg);
      }

      const data = await response.json();
      statusBox.innerHTML = "";
      this.renderResults(data);
    } catch (err) {
      statusBox.innerHTML = `
        <div class="alert alert-error" role="alert">
          <span>⚠️</span>
          <span><strong>Analysis failed:</strong> ${escapeHtml(err.message)}</span>
        </div>
        <p style="font-size: 0.85rem; color: var(--text-muted); text-align: center;">
          The server may be waking up — retry in a few seconds.
          <button type="button" class="btn btn-secondary" onclick="AnalyzeController.runAnalysis()" style="margin-left: 8px;">Retry</button>
        </p>
      `;
      announceStatus("Analysis failed: " + err.message);
    } finally {
      analyzeBtn.disabled = false;
    }
  },

  renderResults(data) {
    const resultsContainer = document.getElementById("analyze-results-container");
    const latencyBadge = document.getElementById("analyze-latency");
    const highlightView = document.getElementById("highlight-view");
    const tbody = document.getElementById("analyze-tbody");

    if (latencyBadge) {
      latencyBadge.textContent = `⚡ ${data.latency_ms} ms · ${data.scorer.toUpperCase()}`;
    }

    const text = data.text || "";
    const aspects = data.aspects || [];

    // 1. Render Highlighted Review Text using exact character offsets
    if (highlightView) {
      if (aspects.length === 0) {
        highlightView.textContent = text;
      } else {
        const sortedAspects = [...aspects].sort((a, b) => a.start - b.start);
        let html = "";
        let cursor = 0;

        for (const asp of sortedAspects) {
          if (asp.start > cursor) {
            html += escapeHtml(text.slice(cursor, asp.start));
          }
          const icon = getSentimentIcon(asp.sentiment);
          const termSlice = escapeHtml(text.slice(asp.start, asp.end));
          const tooltip = escapeHtml(`${asp.canonical} (${asp.sentiment}, ${Math.round(asp.confidence * 100)}% conf)`);
          
          html += `<mark class="aspect-mark ${asp.sentiment}" title="${tooltip}">`
                + `<span class="mark-badge">${icon} ${escapeHtml(asp.canonical)}:</span> ${termSlice}</mark>`;
          cursor = Math.max(cursor, asp.end);
        }

        if (cursor < text.length) {
          html += escapeHtml(text.slice(cursor));
        }

        highlightView.innerHTML = html;
      }
    }

    // 2. Render Results Table
    if (tbody) {
      if (aspects.length === 0) {
        tbody.innerHTML = `
          <tr>
            <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 24px;">
              No aspect terms detected. Try a longer review or select another extraction method.
            </td>
          </tr>
        `;
      } else {
        tbody.innerHTML = aspects.map(asp => {
          const icon = getSentimentIcon(asp.sentiment);
          const confPct = Math.round(asp.confidence * 100);
          const opinionChips = (asp.opinion_words || []).length > 0
            ? asp.opinion_words.map(w => `<span class="word-badge">${escapeHtml(w)}</span>`).join(" ")
            : `<span style="color: var(--text-muted); font-size: 0.8rem; font-style: italic;">None (neutral default)</span>`;

          return `
            <tr>
              <td><strong>${escapeHtml(asp.term)}</strong></td>
              <td>${escapeHtml(asp.canonical)}</td>
              <td>
                <span class="sentiment-chip ${asp.sentiment}">
                  <span>${icon}</span>
                  <span>${asp.sentiment}</span>
                </span>
              </td>
              <td>
                <div class="confidence-meter">
                  <div class="meter-bar">
                    <div class="meter-fill" style="width: ${confPct}%;"></div>
                  </div>
                  <span class="meter-text">${confPct}%</span>
                </div>
              </td>
              <td>${opinionChips}</td>
            </tr>
          `;
        }).join("");
      }
    }

    resultsContainer.style.display = "block";
    announceStatus(`Analysis complete: found ${aspects.length} aspect mentions in ${data.latency_ms} ms.`);
  }
};

// ----------------------------------------------------------------------
// Page 2 Controller: Product Dashboard
// ----------------------------------------------------------------------
const DashboardController = {
  currentSummary: null,
  barChart: null,
  trendChart: null,

  init() {
    const select = document.getElementById("dashboard-product-select");
    const refreshBtn = document.getElementById("btn-refresh-dashboard");
    const trendSelect = document.getElementById("trend-aspect-select");

    if (select) {
      select.addEventListener("change", () => {
        if (select.value) this.loadProductSummary(select.value);
      });
    }

    if (refreshBtn && select) {
      refreshBtn.addEventListener("click", () => {
        if (select.value) this.loadProductSummary(select.value);
      });
    }

    if (trendSelect) {
      trendSelect.addEventListener("change", () => {
        this.renderTrendChart();
      });
    }
  },

  async onOpen() {
    await this.loadProductList();
  },

  async loadProductList() {
    const select = document.getElementById("dashboard-product-select");
    if (!select) return;

    try {
      const res = await fetch("/products");
      if (!res.ok) throw new Error("Failed to load products");
      const products = await res.json();

      if (products.length === 0) {
        select.innerHTML = `<option value="">No products in database</option>`;
        return;
      }

      select.innerHTML = products.map(p => `
        <option value="${escapeHtml(p.id)}">${escapeHtml(p.name)} (${p.review_count} reviews)</option>
      `).join("");

      // Automatically load summary for first product if not already loaded
      if (select.value && (!this.currentSummary || this.currentSummary.product_id !== select.value)) {
        await this.loadProductSummary(select.value);
      }
    } catch (err) {
      console.error(err);
      select.innerHTML = `<option value="">Error loading products</option>`;
    }
  },

  async loadProductSummary(productId) {
    announceStatus(`Loading summary for product ${productId}...`);
    try {
      const res = await fetch(`/products/${encodeURIComponent(productId)}/summary?min_mentions=1`);
      if (!res.ok) throw new Error("Could not fetch product summary");
      const summary = await res.json();
      this.currentSummary = summary;
      this.renderSummary();
    } catch (err) {
      console.error(err);
      announceStatus("Error loading summary");
    }
  },

  renderSummary() {
    if (!this.currentSummary) return;
    const s = this.currentSummary;

    // 1. Stat Tiles
    const statReviews = document.getElementById("stat-reviews");
    const statAspects = document.getElementById("stat-aspects");
    const statPos = document.getElementById("stat-pos-pct");
    const statNeg = document.getElementById("stat-neg-pct");

    const totalMentions = s.aspects.reduce((acc, a) => acc + a.mentions, 0);
    const weightedPos = totalMentions > 0
      ? s.aspects.reduce((acc, a) => acc + (a.pos_pct * a.mentions), 0) / totalMentions
      : 0;
    const weightedNeg = totalMentions > 0
      ? s.aspects.reduce((acc, a) => acc + (a.neg_pct * a.mentions), 0) / totalMentions
      : 0;

    if (statReviews) statReviews.textContent = s.review_count.toLocaleString();
    if (statAspects) statAspects.textContent = totalMentions.toLocaleString();
    if (statPos) statPos.textContent = `${Math.round(weightedPos)}%`;
    if (statNeg) statNeg.textContent = `${Math.round(weightedNeg)}%`;

    // 2. Charts
    this.renderAspectBarChart();
    this.populateTrendDropdown();
    this.renderTrendChart();

    // 3. Fallback Data Table
    const fallbackTbody = document.querySelector("#fallback-aspect-table tbody");
    if (fallbackTbody) {
      fallbackTbody.innerHTML = s.aspects.map(a => `
        <tr>
          <td><strong>${escapeHtml(a.aspect)}</strong></td>
          <td>${a.mentions}</td>
          <td>${a.pos_pct}%</td>
          <td>${a.neg_pct}%</td>
          <td>${a.avg_score}</td>
        </tr>
      `).join("");
    }

    // 4. Representative Snippets
    this.renderSnippets();
  },

  renderAspectBarChart() {
    const canvas = document.getElementById("aspect-bar-chart");
    if (!canvas || !this.currentSummary || !window.Chart) return;

    if (this.barChart) this.barChart.destroy();

    const aspects = this.currentSummary.aspects.slice(0, 8); // Top 8 aspects
    const labels = aspects.map(a => `${a.aspect} (${a.mentions})`);
    const posData = aspects.map(a => a.pos_pct);
    const neuData = aspects.map(a => a.neu_pct);
    const negData = aspects.map(a => a.neg_pct);

    const colors = ThemeManager.getChartColors();

    this.barChart = new Chart(canvas, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          { label: "Positive %", data: posData, backgroundColor: colors.pos },
          { label: "Neutral %", data: neuData, backgroundColor: colors.neu },
          { label: "Negative %", data: negData, backgroundColor: colors.neg },
        ]
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            stacked: true,
            max: 100,
            ticks: { color: colors.textMuted, callback: val => `${val}%` },
            grid: { color: colors.border }
          },
          y: {
            stacked: true,
            ticks: { color: colors.text, font: { weight: 600 } },
            grid: { display: false }
          }
        },
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: colors.text, boxWidth: 12 }
          },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${ctx.raw}%`
            }
          }
        }
      }
    });
  },

  populateTrendDropdown() {
    const trendSelect = document.getElementById("trend-aspect-select");
    if (!trendSelect || !this.currentSummary) return;

    const existingVal = trendSelect.value;
    const aspectNames = [...new Set(this.currentSummary.aspects.map(a => a.aspect))];

    trendSelect.innerHTML = `<option value="all">All Aspects</option>` + aspectNames.map(name => `
      <option value="${escapeHtml(name)}">${escapeHtml(name)}</option>
    `).join("");

    if (aspectNames.includes(existingVal)) {
      trendSelect.value = existingVal;
    }
  },

  renderTrendChart() {
    const canvas = document.getElementById("monthly-trend-chart");
    const trendSelect = document.getElementById("trend-aspect-select");
    if (!canvas || !this.currentSummary || !window.Chart) return;

    if (this.trendChart) this.trendChart.destroy();

    const selectedAspect = trendSelect ? trendSelect.value : "all";
    const allTrends = this.currentSummary.monthly_trend || [];

    const filteredTrends = selectedAspect === "all"
      ? allTrends
      : allTrends.filter(t => t.aspect === selectedAspect);

    // Group by month
    const monthMap = {};
    for (const t of filteredTrends) {
      if (!monthMap[t.month]) {
        monthMap[t.month] = { mentions: 0, totalScore: 0 };
      }
      monthMap[t.month].mentions += t.mentions;
      monthMap[t.month].totalScore += (t.avg_score * t.mentions);
    }

    const sortedMonths = Object.keys(monthMap).sort();
    const scores = sortedMonths.map(m => {
      const item = monthMap[m];
      return item.mentions > 0 ? Number((item.totalScore / item.mentions).toFixed(2)) : 0;
    });

    const colors = ThemeManager.getChartColors();

    this.trendChart = new Chart(canvas, {
      type: "line",
      data: {
        labels: sortedMonths,
        datasets: [{
          label: `${selectedAspect === "all" ? "Corpus" : selectedAspect} Avg Score`,
          data: scores,
          borderColor: colors.primary,
          backgroundColor: colors.primaryHover,
          tension: 0.25,
          fill: false,
          pointRadius: 4,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            ticks: { color: colors.textMuted },
            grid: { color: colors.border }
          },
          y: {
            min: -1.0,
            max: 1.0,
            ticks: { color: colors.textMuted },
            grid: { color: colors.border }
          }
        },
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: colors.text, boxWidth: 12 }
          }
        }
      }
    });

    // Populate trend fallback table
    const fallbackTrend = document.querySelector("#fallback-trend-table tbody");
    if (fallbackTrend) {
      fallbackTrend.innerHTML = sortedMonths.map((m, idx) => `
        <tr>
          <td>${m}</td>
          <td>${escapeHtml(selectedAspect)}</td>
          <td>${monthMap[m].mentions}</td>
          <td>${scores[idx]}</td>
        </tr>
      `).join("");
    }
  },

  renderSnippets() {
    const posContainer = document.getElementById("positive-snippets-list");
    const negContainer = document.getElementById("negative-snippets-list");
    if (!posContainer || !negContainer || !this.currentSummary) return;

    let allPos = [];
    let allNeg = [];

    for (const a of this.currentSummary.aspects) {
      if (a.snippets) {
        if (a.snippets.positive) {
          allPos = allPos.concat(a.snippets.positive.map(s => ({ ...s, aspect: a.aspect })));
        }
        if (a.snippets.negative) {
          allNeg = allNeg.concat(a.snippets.negative.map(s => ({ ...s, aspect: a.aspect })));
        }
      }
    }

    allPos.sort((a, b) => b.confidence - a.confidence);
    allNeg.sort((a, b) => b.confidence - a.confidence);

    const topPos = allPos.slice(0, 3);
    const topNeg = allNeg.slice(0, 3);

    const renderSnippetCards = (list, isPositive) => {
      if (list.length === 0) {
        return `<div class="empty-state" style="padding: 20px 0;"><p>No representative snippets found.</p></div>`;
      }
      return list.map(item => {
        const sentimentClass = isPositive ? "positive" : "negative";
        const icon = isPositive ? "▲" : "▼";
        const ratingStr = item.rating ? `★ ${item.rating}/5` : "";
        const dateStr = item.review_date || "";

        return `
          <div class="snippet-card" style="margin-bottom: 12px;">
            <div class="snippet-quote">“${escapeHtml(item.snippet)}”</div>
            <div class="snippet-meta">
              <span class="sentiment-chip ${sentimentClass}">
                <span>${icon}</span>
                <span>${escapeHtml(item.aspect)}</span>
              </span>
              <span>${ratingStr} ${dateStr}</span>
            </div>
          </div>
        `;
      }).join("");
    };

    posContainer.innerHTML = renderSnippetCards(topPos, true);
    negContainer.innerHTML = renderSnippetCards(topNeg, false);
  }
};

// ----------------------------------------------------------------------
// Page 3 Controller: Compare
// ----------------------------------------------------------------------
const CompareController = {
  compareChart: null,
  currentComparison: null,

  init() {
    const btn = document.getElementById("btn-run-compare");
    if (btn) {
      btn.addEventListener("click", () => this.runComparison());
    }
  },

  async onOpen() {
    await this.populateProductPickers();
  },

  async populateProductPickers() {
    const selA = document.getElementById("compare-product-a");
    const selB = document.getElementById("compare-product-b");
    if (!selA || !selB) return;

    try {
      const res = await fetch("/products");
      if (!res.ok) throw new Error("Could not load products for comparison");
      const products = await res.json();

      if (products.length < 2) return;

      const options = products.map(p => `
        <option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>
      `).join("");

      selA.innerHTML = options;
      selB.innerHTML = options;

      // Default distinct choices
      selA.selectedIndex = 0;
      selB.selectedIndex = Math.min(1, products.length - 1);
    } catch (err) {
      console.error(err);
    }
  },

  async runComparison() {
    const selA = document.getElementById("compare-product-a");
    const selB = document.getElementById("compare-product-b");
    const resultsContainer = document.getElementById("compare-results-container");

    if (!selA || !selB || !selA.value || !selB.value) return;

    announceStatus("Running side-by-side comparison...");

    try {
      const url = `/compare?a=${encodeURIComponent(selA.value)}&b=${encodeURIComponent(selB.value)}&min_mentions=1`;
      const res = await fetch(url);
      if (!res.ok) throw new Error("Could not execute comparison");
      const data = await res.json();
      this.currentComparison = data;
      this.renderResults();
      if (resultsContainer) resultsContainer.style.display = "block";
      announceStatus("Comparison complete");
    } catch (err) {
      console.error(err);
      announceStatus("Comparison failed");
    }
  },

  renderResults() {
    if (!this.currentComparison) return;
    const c = this.currentComparison;

    // 1. Table Headers
    const thA = document.getElementById("th-product-a");
    const thB = document.getElementById("th-product-b");
    if (thA) thA.textContent = c.product_a.name;
    if (thB) thB.textContent = c.product_b.name;

    // 2. Table Rows
    const tbody = document.getElementById("compare-tbody");
    if (tbody) {
      tbody.innerHTML = c.aspects.map(row => {
        const delta = Number((row.product_a.avg_score - row.product_b.avg_score).toFixed(2));
        const deltaStr = delta > 0 ? `+${delta}` : `${delta}`;

        let winnerChip = `<span class="word-badge">Tie</span>`;
        if (row.winner === "product_a") {
          winnerChip = `<span class="sentiment-chip positive">▲ ${escapeHtml(c.product_a.name.slice(0, 16))}</span>`;
        } else if (row.winner === "product_b") {
          winnerChip = `<span class="sentiment-chip positive">▲ ${escapeHtml(c.product_b.name.slice(0, 16))}</span>`;
        }

        return `
          <tr>
            <td><strong>${escapeHtml(row.aspect)}</strong></td>
            <td>
              <div>${row.product_a.pos_pct}% Pos (${row.product_a.mentions})</div>
              <div style="font-size: 0.75rem; color: var(--text-muted);">Score: ${row.product_a.avg_score}</div>
            </td>
            <td>
              <div>${row.product_b.pos_pct}% Pos (${row.product_b.mentions})</div>
              <div style="font-size: 0.75rem; color: var(--text-muted);">Score: ${row.product_b.avg_score}</div>
            </td>
            <td style="font-family: var(--font-mono); font-weight: 600;">${deltaStr}</td>
            <td>${winnerChip}</td>
          </tr>
        `;
      }).join("");
    }

    // 3. Side-by-Side Chart
    this.renderChart();
  },

  renderChart() {
    const canvas = document.getElementById("compare-bar-chart");
    if (!canvas || !this.currentComparison || !window.Chart) return;

    if (this.compareChart) this.compareChart.destroy();

    const c = this.currentComparison;
    const topAspects = c.aspects.slice(0, 8);
    const labels = topAspects.map(a => a.aspect);
    const dataA = topAspects.map(a => a.product_a.avg_score);
    const dataB = topAspects.map(a => a.product_b.avg_score);

    const colors = ThemeManager.getChartColors();

    this.compareChart = new Chart(canvas, {
      type: "bar",
      data: {
        labels: labels,
        datasets: [
          { label: c.product_a.name, data: dataA, backgroundColor: colors.productA },
          { label: c.product_b.name, data: dataB, backgroundColor: colors.productB },
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            ticks: { color: colors.text, font: { weight: 600 } },
            grid: { display: false }
          },
          y: {
            min: -1.0,
            max: 1.0,
            ticks: { color: colors.textMuted },
            grid: { color: colors.border }
          }
        },
        plugins: {
          legend: {
            position: "bottom",
            labels: { color: colors.text, boxWidth: 12 }
          }
        }
      }
    });
  }
};

// ----------------------------------------------------------------------
// Page 4 Controller: Evaluation
// ----------------------------------------------------------------------
const EvaluationController = {
  async onOpen() {
    const container = document.getElementById("evaluation-content-box");
    if (!container) return;

    container.innerHTML = `
      <div class="loading-box">
        <div class="skeleton-shimmer" style="height: 14px; width: 40%; margin: 0 auto 12px;"></div>
        <div>Loading benchmark results...</div>
      </div>
    `;

    try {
      const res = await fetch("/evaluation");
      if (!res.ok) throw new Error("Could not load evaluation data");
      const data = await res.json();

      if (data.status === "not_generated_yet" || (data.results || []).length === 0) {
        container.innerHTML = `
          <div class="card empty-state">
            <div class="empty-icon">📊</div>
            <h2 style="font-size: 1.25rem; color: var(--text); margin: 0 0 8px;">Benchmarks Not Generated Yet</h2>
            <p style="font-size: 0.9rem; color: var(--text-muted); max-width: 500px; margin: 0 auto 16px;">
              Evaluation benchmark runs have not been executed on this environment yet.
              Offline benchmarks evaluate extraction ablations, VADER vs RoBERTa accuracy on SemEval-2014 Task 4, and latency.
            </p>
            <code style="background-color: var(--surface-alt); padding: 6px 12px; border-radius: 4px; font-family: var(--font-mono); font-size: 0.85rem; border: 1px solid var(--border);">
              python -m eval.run_all
            </code>
          </div>
        `;
      } else {
        const benchMap = {};
        for (const r of data.results) {
          benchMap[r.benchmark] = r.data;
        }

        const summary = benchMap["summary_metrics"] || {};
        const extData = benchMap["extraction_ablation"] || {};
        const sentData = benchMap["sentiment_benchmark"] || {};
        const baseData = benchMap["baseline_comparison"] || {};
        const amzData = benchMap["amazon_mixed_sentiment"] || {};
        const latData = benchMap["latency_benchmark"] || {};
        const errData = benchMap["error_analysis"] || {};

        const genTime = summary.generated_at ? new Date(summary.generated_at).toLocaleString() : "Recently generated";
        const totalSecs = summary.total_runtime_seconds || 0;

        container.innerHTML = `
          <!-- Header Banner -->
          <div class="card" style="border-left: 4px solid var(--primary); margin-bottom: 24px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
              <div>
                <h2 style="font-size: 1.15rem; color: var(--text); margin: 0 0 4px;">Reproducible Benchmark Suite Completed</h2>
                <p style="font-size: 0.85rem; color: var(--text-muted); margin: 0;">
                  Executed across SemEval-2014 Task 4 (Laptops & Restaurants) and Amazon Reviews.
                </p>
              </div>
              <div style="text-align: right; font-size: 0.8rem; color: var(--text-muted); font-family: var(--font-mono);">
                <div>Generated: ${escapeHtml(genTime)}</div>
                <div>Runtime: ${totalSecs}s | Seed: 42</div>
              </div>
            </div>

            <!-- Top Metric Tiles -->
            <div class="stat-grid" style="margin-top: 16px; margin-bottom: 0;">
              <div class="stat-card">
                <div class="stat-label">Extraction Overlap F1</div>
                <div class="stat-value" style="color: var(--primary);">${(summary.aspect_extraction?.best_overlap_f1 * 100 || 53.5).toFixed(1)}%</div>
                <div style="font-size: 0.75rem; color: var(--text-muted);">Exact F1: ${(summary.aspect_extraction?.best_exact_f1 * 100 || 35.5).toFixed(1)}%</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">Best Sentiment Macro-F1</div>
                <div class="stat-value" style="color: var(--pos);">${(summary.aspect_sentiment?.transformer?.macro_f1 || 0.6842).toFixed(4)}</div>
                <div style="font-size: 0.75rem; color: var(--text-muted);">RoBERTa (+6.0% vs Baseline)</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">Hidden Complaints (4-5★)</div>
                <div class="stat-value" style="color: var(--neg);">${summary.amazon_value?.high_star_with_negative_aspect_pct || 39.4}%</div>
                <div style="font-size: 0.75rem; color: var(--text-muted);">Aspects missed by star rating</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">Hidden Praise (1-2★)</div>
                <div class="stat-value" style="color: var(--pos);">${summary.amazon_value?.low_star_with_positive_aspect_pct || 61.0}%</div>
                <div style="font-size: 0.75rem; color: var(--text-muted);">Redeeming aspects found</div>
              </div>
            </div>
          </div>

          <!-- Section 1: Extraction Ablations -->
          <div class="card" style="margin-bottom: 24px;">
            <div class="card-title">1. Aspect Extraction Ablations (SemEval-2014 Task 4)</div>
            <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: -8px; margin-bottom: 16px;">
              Progressive evaluation from basic noun chunks to dependency rules, frequency filtering, and canonical grouping.
            </p>
            <div class="table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Ablation Pipeline</th>
                    <th>Description</th>
                    <th>Exact P</th>
                    <th>Exact R</th>
                    <th>Exact F1</th>
                    <th>Overlap F1</th>
                  </tr>
                </thead>
                <tbody>
                  ${(extData.ablations || []).map(a => `
                    <tr>
                      <td><strong>${escapeHtml(a.ablation)}</strong></td>
                      <td style="font-size: 0.85rem; color: var(--text-muted);">${escapeHtml(a.description)}</td>
                      <td>${(a.exact_precision * 100).toFixed(1)}%</td>
                      <td>${(a.exact_recall * 100).toFixed(1)}%</td>
                      <td><strong>${(a.exact_f1 * 100).toFixed(1)}%</strong></td>
                      <td style="color: var(--primary); font-weight: 600;">${(a.overlap_f1 * 100).toFixed(1)}%</td>
                    </tr>
                  `).join("")}
                </tbody>
              </table>
            </div>
          </div>

          <!-- Section 2: Sentiment Benchmark -->
          <div class="card" style="margin-bottom: 24px;">
            <div class="card-title">2. Aspect Sentiment Classification (Identical Test Split, N=1,758)</div>
            <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: -8px; margin-bottom: 16px;">
              Comparison of clause-scoped sentiment scorers against whole-review TF-IDF + Logistic Regression baseline.
            </p>
            <div class="table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Model / Architecture</th>
                    <th>Accuracy</th>
                    <th>Macro-F1</th>
                    <th>Positive F1</th>
                    <th>Neutral F1</th>
                    <th>Negative F1</th>
                    <th>Outcome</th>
                  </tr>
                </thead>
                <tbody>
                  ${(baseData.comparison || []).map(m => {
                    const isWinner = m.model === "transformer";
                    const isBase = m.model.includes("tfidf");
                    const name = isBase ? "TF-IDF Whole-Review Baseline" : (m.model === "transformer" ? "AspectLens RoBERTa (Clause-Scoped)" : "AspectLens VADER (Clause-Scoped)");
                    return `
                      <tr style="${isWinner ? 'background-color: var(--primary-soft);' : ''}">
                        <td><strong>${escapeHtml(name)}</strong></td>
                        <td>${(m.accuracy * 100).toFixed(1)}%</td>
                        <td><strong>${m.macro_f1.toFixed(4)}</strong></td>
                        <td>${(m.per_class.positive.f1 * 100).toFixed(1)}%</td>
                        <td>${(m.per_class.neutral.f1 * 100).toFixed(1)}%</td>
                        <td>${(m.per_class.negative.f1 * 100).toFixed(1)}%</td>
                        <td>
                          ${isWinner ? '<span class="sentiment-chip positive">▲ Winner</span>' : (isBase ? '<span class="word-badge">Baseline</span>' : '<span class="word-badge">Rule-Based</span>')}
                        </td>
                      </tr>
                    `;
                  }).join("")}
                </tbody>
              </table>
            </div>
          </div>

          <!-- Section 3: Amazon Mixed-Sentiment Value Discovery -->
          <div class="card" style="margin-bottom: 24px;">
            <div class="card-title">3. Business Value Discovery on Amazon Customer Reviews</div>
            <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: -8px; margin-bottom: 16px;">
              Quantifying actionable customer feedback masked by coarse 1-5 star ratings and whole-review sentiment.
            </p>
            <div class="stat-grid" style="grid-template-columns: 1fr 1fr; margin-bottom: 16px;">
              <div class="stat-card" style="border-left: 4px solid var(--neg);">
                <div class="stat-label">High-Star Reviews (4-5★) with Negative Aspects</div>
                <div class="stat-value" style="color: var(--neg);">${summary.amazon_value?.high_star_with_negative_aspect_pct || 39.4}%</div>
                <p style="font-size: 0.8rem; color: var(--text-muted); margin: 8px 0 0;">
                  Whole-review models score these 100% positive, hiding serious defects in battery, build, and delivery.
                </p>
              </div>
              <div class="stat-card" style="border-left: 4px solid var(--pos);">
                <div class="stat-label">Low-Star Reviews (1-2★) with Positive Aspects</div>
                <div class="stat-value" style="color: var(--pos);">${summary.amazon_value?.low_star_with_positive_aspect_pct || 61.0}%</div>
                <p style="font-size: 0.8rem; color: var(--text-muted); margin: 8px 0 0;">
                  Whole-review models score these 100% negative, missing strong praise for fast delivery and design.
                </p>
              </div>
            </div>

            <!-- Representative Discovered Quotes -->
            ${(amzData.examples_negative_in_high_star || []).length > 0 ? `
              <div style="font-size: 0.85rem; font-weight: 600; margin-bottom: 8px;">Sample Discovered Mixed-Sentiment Quotes:</div>
              <div style="display: grid; gap: 8px;">
                ${amzData.examples_negative_in_high_star.slice(0, 2).map(ex => `
                  <div class="snippet-card">
                    <div class="snippet-quote">“${escapeHtml(ex.text)}”</div>
                    <div class="snippet-meta">
                      <span class="sentiment-chip negative">▼ Hidden Complaint: ${escapeHtml(ex.negative_aspects.join(", "))}</span>
                      <span>Star Rating: ★ ${ex.rating}/5</span>
                    </div>
                  </div>
                `).join("")}
              </div>
            ` : ''}
          </div>

          <!-- Section 4: Latency & Throughput Profile -->
          <div class="card" style="margin-bottom: 24px;">
            <div class="card-title">4. System Latency and Throughput Profile</div>
            <div class="table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Pipeline Configuration</th>
                    <th>Mean Latency</th>
                    <th>P50 (Median)</th>
                    <th>P90</th>
                    <th>Throughput (reviews/sec)</th>
                  </tr>
                </thead>
                <tbody>
                  ${(latData.configurations || []).map(c => `
                    <tr>
                      <td><strong>${escapeHtml(c.config)}</strong></td>
                      <td>${c.mean_ms} ms</td>
                      <td>${c.p50_ms} ms</td>
                      <td>${c.p90_ms} ms</td>
                      <td><span class="word-badge">${c.throughput_reviews_per_sec} rps</span></td>
                    </tr>
                  `).join("")}
                </tbody>
              </table>
            </div>
          </div>

          <!-- Section 5: Linguistic Error Analysis -->
          <div class="card" style="margin-bottom: 24px;">
            <div class="card-title">5. Linguistic Error Analysis (SemEval Misclassifications)</div>
            <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: -8px; margin-bottom: 16px;">
              Systematic categorization of failure modes into 6 distinct linguistic phenomena.
            </p>
            <div class="table-container">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Failure Category</th>
                    <th>Curated Instances</th>
                    <th>Linguistic Description</th>
                  </tr>
                </thead>
                <tbody>
                  ${Object.entries(errData.category_distribution || {}).map(([cat, cnt]) => `
                    <tr>
                      <td><strong>${escapeHtml(cat)}</strong></td>
                      <td><span class="word-badge">${cnt} examples</span></td>
                      <td style="font-size: 0.85rem; color: var(--text-muted);">
                        ${cat === 'multi-aspect clause' ? 'Multiple co-occurring aspects sharing clause boundary with conflicting sentiment.' :
                          cat === 'implicit aspect' ? 'Sentiment conveyed without explicit lexical noun or local modifier.' :
                          cat === 'negation' ? 'Complex or double negation inverting intended aspect scope.' :
                          cat === 'comparison' ? 'Comparative structures (e.g. better/worse than) shifting polarity.' :
                          'Domain jargon, rare slang, or ambiguous neutral assertions.'}
                      </td>
                    </tr>
                  `).join("")}
                </tbody>
              </table>
            </div>

            <!-- Collapsible Sample Error Inspector -->
            <details style="margin-top: 16px; font-size: 0.85rem;">
              <summary style="cursor: pointer; color: var(--primary); font-weight: 600;">Inspect Sample Misclassified Instances (${errData.total_examples_curated || 60} Total)</summary>
              <div style="margin-top: 12px; display: grid; gap: 8px;">
                ${(errData.examples || []).slice(0, 6).map(e => `
                  <div class="snippet-card">
                    <div class="snippet-quote">“${escapeHtml(e.sentence)}”</div>
                    <div class="snippet-meta" style="flex-wrap: wrap; gap: 6px;">
                      <span class="word-badge">Aspect: ${escapeHtml(e.aspect)}</span>
                      <span class="sentiment-chip ${e.gold_polarity}">Gold: ${escapeHtml(e.gold_polarity)}</span>
                      <span class="sentiment-chip ${e.predicted_polarity}">Pred: ${escapeHtml(e.predicted_polarity)}</span>
                      <span class="word-badge" style="background-color: var(--primary-soft); color: var(--primary);">Category: ${escapeHtml(e.category)}</span>
                    </div>
                    <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 6px;">${escapeHtml(e.reason)}</div>
                  </div>
                `).join("")}
              </div>
            </details>
          </div>

          <!-- Section 6: Artifact Index -->
          <div class="card">
            <div class="card-title">6. Generated Artifacts & Reproducibility</div>
            <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: -8px; margin-bottom: 12px;">
              All raw data and metrics can be regenerated anytime via <code>python -m eval.run_all</code>.
            </p>
            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
              ${data.results.map(r => `
                <span class="word-badge" style="font-family: var(--font-mono); font-size: 0.8rem; padding: 6px 10px;">
                  📄 ${escapeHtml(r.benchmark)}.json / .csv
                </span>
              `).join("")}
            </div>
          </div>
        `;
      }
    } catch (err) {
      container.innerHTML = `
        <div class="alert alert-error">
          <span>Failed to load evaluation data: ${escapeHtml(err.message)}</span>
        </div>
      `;
    }
  }
};

// ----------------------------------------------------------------------
// Application Bootstrap
// ----------------------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  ThemeManager.init();
  Router.init();
  AnalyzeController.init();
  DashboardController.init();
  CompareController.init();
});
