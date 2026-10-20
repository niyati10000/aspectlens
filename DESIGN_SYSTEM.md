# DESIGN_SYSTEM.md — AspectLens UI

Plain HTML + CSS + JS, Chart.js, no build step. Everything below is implemented as **CSS custom properties** in `frontend/style.css`.

## 1. Principles
1. **Clarity over decoration** — it's an analytics tool; data is the hero.
2. **Sentiment is never color-only** — always pair color with an icon/label (accessibility).
3. **Counts beside percentages** — never show a % without its mention count.
4. **Every state designed** — loading, empty, error, success.
5. **Honest** — show confidence and limitations, not just pretty charts.

## 2. Color tokens
```css
:root {
  /* surface */
  --bg: #F7F8FA;  --surface: #FFFFFF;  --border: #E2E5EA;
  --text: #1B1F27; --text-muted: #5B6472;
  /* brand */
  --primary: #3B5BDB; --primary-hover: #2F4AC0; --primary-soft: #E7ECFF;
  /* sentiment */
  --pos: #1F8A4C;  --pos-soft: #E3F4EA;
  --neg: #C92A2A;  --neg-soft: #FBE7E7;
  --neu: #6B7280;  --neu-soft: #ECEEF1;
  /* feedback */
  --warn: #B7791F; --focus: #3B5BDB;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg:#0F1218; --surface:#171B23; --border:#2A303B;
    --text:#EEF1F6; --text-muted:#9AA3B2;
    --primary:#7C95FF; --primary-hover:#9AAEFF; --primary-soft:#1E2542;
    --pos:#4CC38A; --pos-soft:#12301F;
    --neg:#FF6B6B; --neg-soft:#3A1717;
    --neu:#9AA3B2; --neu-soft:#232832;
  }
}
```
Contrast target: text ≥ 4.5:1, UI components ≥ 3:1 (verify in both themes).

## 3. Typography
- Font stack: `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif` (no web-font dependency). Mono: `ui-monospace, Menlo, Consolas`.
- Scale: 12 / 14 / 16 (base) / 20 / 24 / 32 px. Line-height 1.5 body, 1.25 headings.
- Weights: 400 body, 600 headings/labels.

## 4. Spacing, radius, elevation
- Spacing scale (px): 4, 8, 12, 16, 24, 32, 48.
- Radius: 6 (inputs/chips), 12 (cards).
- Shadow: `0 1px 2px rgba(0,0,0,.06)`; no heavy shadows.
- Max content width 1100px; centered.

## 5. Layout
- Top nav with 5 tabs: **Analyze · Product Dashboard · Compare · Evaluation · About**. Sticky; collapses to a horizontal scroll/menu < 640px.
- Breakpoints: 640 / 960. Grid: 1 col mobile, 2 col ≥ 960 for charts.
- Hash-based routing (`#/analyze`) so refresh keeps the page; no framework.

## 6. Components
| Component | Spec |
|---|---|
| Button | primary (filled), secondary (outline); 40px height; visible focus ring `2px var(--focus)` |
| Input / textarea | label above, 1px border, 12px padding, char counter on review box |
| Select | native `<select>` styled; used for scorer + product pickers |
| Card | surface bg, 1px border, 12px radius, 16–24px padding |
| **Aspect highlight** | `<mark>` with soft bg + 2px bottom border: `--pos-soft/--pos`, `--neg-soft/--neg`, `--neu-soft/--neu`; tooltip shows aspect + confidence; positioned using API char offsets |
| **Sentiment chip** | rounded pill: icon (▲ pos, ▼ neg, ● neutral) + text label |
| Result table | columns: Aspect · Sentiment · Confidence (bar + %) · Opinion words (chips) |
| Stat tile | big number + label + mention count |
| Chart | Chart.js; stacked horizontal bars (pos/neg/neu share), monthly line; legend visible; text alternative table below via `<details>` |
| Snippet card | quoted sentence, aspect chip, sentiment chip |
| Toast / inline alert | info / warn / error with icon; `role="alert"` for errors |
| Skeleton loader | grey shimmer blocks (respect `prefers-reduced-motion`) |
| Empty state | icon + one-line explanation + action |

## 7. Pages
1. **Analyze** — textarea (max chars from API config), scorer selector, "Try an example" button (pre-fills the battery/delivery/price review), Analyze button → highlighted review + result table. Show latency.
2. **Product Dashboard** — product picker; stat tiles (reviews, aspects); aspect bar chart (pos vs neg share **with mention counts**); monthly trend line (aspect selector); top 3 positive + negative snippets.
3. **Compare** — two product pickers; side-by-side grouped bar chart + delta table highlighting biggest gaps.
4. **Evaluation** — tables/charts from `/evaluation`: extraction ablation, scorer comparison, whole-review vs aspect-level, latency, error-category breakdown. Show "generated on {date}".
5. **About** — pipeline diagram (steps ↔ syllabus units), limitations, ethics notes, datasets, links to GitHub/README.

## 8. Accessibility checklist
- Semantic HTML (`nav`, `main`, `section`, `table`), one `h1` per page.
- Every input has a `<label>`; errors tied via `aria-describedby`.
- Full keyboard navigation; visible focus; tab order logical; skip-to-content link.
- Color + icon + text for sentiment; charts have table fallbacks.
- `aria-live="polite"` on result regions and loading text.
- Respect `prefers-reduced-motion` and `prefers-color-scheme`.
- Touch targets ≥ 44px on mobile.

## 9. Microcopy
- Loading: "Reading the review…" · Empty: "No aspects found. Try a longer review or a different scorer." · Error: plain language + retry (e.g. "The server is waking up — this can take up to a minute. Retry?").
- Low-sample note: "Based on {n} mentions — interpret with care."
- Neutral/low-confidence: "No clear opinion found."

## 10. Do / Don't
**Do:** consistent sentiment colors everywhere, show mention counts, keep forms short.
**Don't:** rely on color alone, hide limitations, add animation that blocks content, use external CDNs other than Chart.js (pin version + SRI hash, or vendor the file into `frontend/`).
