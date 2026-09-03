# Reconciliation Autopilot — Build Log

*Razorpay AI Buildathon · compiled 3 September 2026 from repository state at `9ec44ae` plus uncommitted working-tree changes.*

## Note on sources

No chat transcripts or runtime logs were retained — this document was assembled fresh from primary evidence in the repository: the four-commit git history, the full uncommitted diff (284 insertions / 570 deletions across 8 files, plus 9 new files), and the source code itself.

The code carries explanatory comments that record *why* each change was made — rate-limit ceilings hit, API approvals that weren't going to arrive in time, false positives traced to their cause. The "Problems hit" section quotes those reasons rather than inferring them. Where something is an inference, it says so.

**Quick facts:** 12 Python modules · 1,161 lines of Python · 1,254 lines of template · 7 flag types · 0 databases · branch `master` · 4 commits.

---

## 1. Tech stack

| Layer | Technology | Role in this project |
|---|---|---|
| Language | Python 3.14 | Whole application; confirmed by `cpython-314` bytecode artifacts |
| Web framework | Flask ≥ 3.0 | Routing, request handling, signed session cookies, dev server |
| WSGI / utils | Werkzeug ≥ 3.0 | `secure_filename` on uploads, request plumbing |
| Templating | Jinja2 | Template inheritance — one `base.html` shell, three page templates, block overrides |
| Payments API | razorpay ≥ 1.4.2 | Official Python SDK; `payment.all()` and `settlement.all()` |
| AI layer | openai ≥ 1.50 | Chat Completions; default model `gpt-5-mini`, overridable via env |
| Concurrency | concurrent.futures | `ThreadPoolExecutor` for parallel LLM calls *and* for client-side call timeouts |
| Thread safety | threading · collections.deque | Lock-guarded sliding-window rate limiter shared process-wide |
| Secrets | python-dotenv | Loads `.env` (gitignored) — three keys: Razorpay ID/secret, OpenAI key |
| Session security | secrets · os.urandom · uuid | `token_urlsafe(24)` credential handles, random cookie signing key, `uuid4` visitor IDs |
| Identity / hashing | hashlib | SHA-1 truncated to 10 chars — stable flag IDs across re-runs |
| Persistence | json · csv | JSON for transactions/settlements/flag state, `csv.DictReader` for merchant orders |
| Frontend — CSS | hand-written, ~700 lines | Custom properties, layered radial gradients, 8 keyframe animations, cubic-bezier easing |
| Frontend — JS | vanilla ES6 | `fetch`, drag-and-drop File API, `requestAnimationFrame` cubic-eased counters |
| Iconography | inline SVG | Hand-authored stroke icons — no icon-font or sprite dependency |
| Typography | Google Fonts | Inter (400–800) for UI, JetBrains Mono (500) for IDs and amounts |
| Tooling | venv · pip · git | `requirements.txt`; `run_all.py` orchestrates mock-data → reconcile → explain → serve |

Two absences are deliberate. There is **no database** — flag decisions live in `data/flag_status.json`, credentials and pending reports live in process memory only. And there is **no frontend framework or bundler** — the dashboard is server-rendered Jinja plus progressive-enhancement JavaScript, so there is nothing to compile before a demo.

---

## 2. How a reconciliation runs

The whole product rests on comparing two records of the same money, written by two different systems, that are never guaranteed to agree:

- **Merchant's own books** — `order_id · amount (paise) · email · order_date`
- **Razorpay's record** — payments: `id · order_id · amount · status`; settlements: `id · amount · transactions[]`

### Stage 1 — Ingest (`fetch_data.py`, uploaded CSV)
Merchant orders arrive as an uploaded CSV. The Razorpay side is either pulled live from the API or read from the demo dataset. Live payments are filtered to `captured` only, and written to separate `live_*.json` files so a live pull never overwrites the demo fixtures.
→ emits `orders[] · payments[] · settlements[]`

### Stage 2 — Exact match (`reconcile.py`)
Indexes payments by `id` and by `order_id`, flattens each settlement into its constituent transactions, then walks every order applying six deterministic rules. Anything that reconciles cleanly goes to `matched`; everything else becomes a flag with a stable SHA-1 ID.
→ emits `matched[] · flags[]`

### Stage 3 — Fuzzy second pass (`fuzzy_match.py`)
Runs *only* on records exact matching already gave up on. Scores every orphan-order × unmatched-payment pair on amount, email and date proximity; each record can be suggested once, against its single best candidate above 0.5 confidence. Exact matching is never overridden.
→ emits `POSSIBLE_MATCH` suggestions with confidence

### Stage 4 — Explain (`explain_flags.py`, `rate_limiter.py`)
Every flag gets a plain-English explanation and a recommended action from the LLM. Calls run in parallel (up to 8), each waiting on a shared 60-per-minute quota before it spends its 8-second timeout budget. Any failure falls back to a hand-written per-flag-type message, and the report records which one you got.
→ emits `ai_explanation · ai_action · explanation_source`

### Stage 5 — Review & decide (`report_store.py`, `flag_status.py`)
The finished report is stashed against the visitor's session ID, and the POST redirects to `GET /reconcile` which consumes it once. The analyst confirms or dismisses each flag; those decisions persist to JSON keyed by the stable flag ID, so re-running on the same data preserves them.
→ emits `pending / confirmed / dismissed`

---

## 3. Detection rules

### Flag taxonomy (6 deterministic + 1 probabilistic)

| Flag | Trigger condition | What it means in practice |
|---|---|---|
| `ORPHAN_ORDER` | Order has no payment carrying its `order_id` | Booked a sale with no money against it |
| `PAYMENT_NOT_SETTLED` | Payment captured, absent from every settlement | Money taken from the customer, not yet paid out |
| `DUPLICATE_SETTLEMENT` | Payment appears in more than one settlement | Possible double credit — the expensive kind of error |
| `AMOUNT_MISMATCH` | Captured amount ≠ settled amount | Usually gateway fees; the delta is reported explicitly |
| `PAYMENT_WITHOUT_ORDER` | Payment's `order_id` matches no CSV row | Money received against nothing on the books |
| `UNKNOWN_SETTLEMENT_TRANSACTION` | Settlement cites a transaction ID not in the payment set | Settlement references something unaccounted for |
| `POSSIBLE_MATCH` | Fuzzy score ≥ 0.50 between an orphan pair | Suggestion, not a finding — carries a confidence percentage |

### Fuzzy confidence scoring

Deliberately deterministic and additive, capped at 1.0 — fully testable without a single API call. The LLM is invited only afterwards, to phrase the reasoning for a candidate that already passed the threshold.

| Signal | Test | Weight |
|---|---|---|
| Amount, exact | Paise values identical | +0.50 |
| Amount, near | Within 1% of the order amount | +0.30 |
| Email | Case-folded, trimmed, identical | +0.30 |
| Date, same day | ≤ 1 day between order date and payment timestamp | +0.20 |
| Date, near | ≤ 3 days apart | +0.10 |
| **Threshold** | Below this, no suggestion is made at all | **0.50** |

Amount alone clears the bar, which is intended: an exact paise match on an unlinked pair is the single strongest signal available. Email or date alone never does.

---

## 4. Functionality, in full

**Account connection**
- Landing page → connect page → dashboard, a three-step flow
- Merchant pastes their own Key ID and Key Secret once
- Credentials verified against Razorpay before being accepted
- Held server-side in memory; the cookie carries only a random token
- Key ID shown masked (`rzp_test••••1234`)
- Explicit disconnect; connected visitors skip the entry pages
- Falls back to the app owner's `.env` keys when nobody has connected

**Getting data in**
- CSV upload by drag-and-drop or file picker, with filename echo
- Extension check plus `secure_filename` sanitisation
- "Use live data" checkbox pulls real payments and settlements
- One-click demo dataset, regenerated deterministically each time
- Live pull degrades to mock data and says so in a banner
- Standalone connectivity check endpoint with sample records

**Reconciliation output**
- Five animated summary counters: matched, flagged, confirmed, dismissed, pending
- Matched list with INR amounts formatted from paise
- Flag cards colour-coded by review state
- Confidence badge on every fuzzy suggestion
- Per-flag AI explanation and recommended action
- Label switches from "AI Explanation" to "Explanation" when a fallback was used
- Empty state until you explicitly act — nothing is pre-baked

**Human in the loop**
- Confirm, dismiss, or undo any flag
- Updates posted via `fetch` — no page reload
- Counters and card styling update live
- Decisions persist to disk
- Stable flag IDs mean a re-run on the same data keeps your decisions
- Server rejects any status outside the three valid values

### HTTP surface

| Route | Method | Behaviour |
|---|---|---|
| `/` | GET | Landing page; redirects to the dashboard if already connected |
| `/connect` | GET | Credential form |
| `/connect` | POST | Verifies keys, mints a session token, redirects |
| `/disconnect` | POST | Drops stored credentials and the cookie token |
| `/reconcile` | GET | Dashboard; consumes any pending report exactly once |
| `/upload` | POST | Runs reconciliation on an uploaded CSV, optionally against live data |
| `/demo` | POST | Regenerates fixtures and reconciles them |
| `/flag/<id>/status` | POST | Records a confirm / dismiss / undo decision |
| `/razorpay/live-check` | GET | Connectivity probe returning counts, cap warnings, and samples |

---

## 5. Build phases

```
37d7c03  30 Aug 2026  checkpoint before Claude edits
44b0ac4  31 Aug 2026  Filter live Razorpay payments to captured-only
afc30c2  1 Sep 2026   Working version before UI overhaul — safe fallback point
9ec44ae  1 Sep 2026   Clean up stale duplicate files and empty src folder
```

**Phase 1 — Core engine and demo fixtures.** The deterministic parts came first: `create_mock_data.py` builds six orders, six payments and five settlements with discrepancies planted on purpose — one order with no payment, one payment settled twice, one settled 120 rupees light, one payment whose `order_id` is `ord_1006_alt` against a CSV row reading `ord_1006`. That last one exists specifically to give the fuzzy matcher something real to catch. `reconcile.py` and the Jinja dashboard were built against these fixtures, so every flag type had a live example from day one.

**Phase 2 — Live Razorpay integration.** The SDK client, live fetch, and the write-to-separate-files decision. Live output goes to `data/live_transactions.json` and `data/live_settlements.json` rather than over the demo fixtures — so a failed or empty live pull can never destroy a working demo. This phase produced the first real bug fix (captured-only filtering, see §7.1) and its own commit.

**Phase 3 — AI explanations and fuzzy matching.** The LLM layer, built fallback-first: hand-written explanations for all six flag types went into `config.py` *before* the API calls were wired up, so the dashboard was never capable of showing a blank or broken message. Fuzzy matching followed the same discipline — scoring deterministic and offline-testable, the model used only for phrasing.

**Phase 4 — Provider migration and throughput work.** The Gemini free tier proved unusable (§7.2). The whole AI layer moved to OpenAI, and while both call sites were open they were also parallelised and put behind a shared rate limiter (§7.3, §7.4). Commit `afc30c2` marks the deliberate safe point taken before the next phase.

**Phase 5 — Multi-tenant connect flow and UI overhaul.** The largest uncommitted change. A single-page tool driven by the developer's own `.env` keys became a three-page product any merchant can connect their own account to. The 470-line `index.html` was deleted and replaced by a `base.html` shell plus `landing`, `connect` and `reconcile` templates; every route was rewritten to resolve credentials per session; and the POST/redirect/GET pattern arrived with it (§7.7). Currently working-tree only — nine new files, not yet committed.

---

## 6. Modifications, by area

*The uncommitted diff against `9ec44ae`: 8 files changed, 9 added, 1 deleted.*

| File | Δ lines | What changed and why |
|---|---|---|
| `app.py` | +144 | Single dashboard route split into landing / connect / reconcile. Added per-visitor session IDs, three credential-resolution helpers, connect and disconnect handlers, POST/redirect/GET on both run paths, and a raised live-check sample ceiling. |
| `config.py` | +33 | Gemini settings block replaced by OpenAI settings; added concurrency cap, RPM ceiling, and a Flask signing key. Timeout tightened 20s → 8s, retries 2 → 1. |
| `explain_flags.py` | +72 / −72 | Rewritten for the OpenAI Chat Completions shape. Sequential per-flag loop became a bounded thread pool; rate-limiter acquisition inserted ahead of the timeout window. |
| `fuzzy_match.py` | +82 / −82 | Same provider migration, plus a structural split: deterministic scoring completes for all candidates first, then reasoning calls fire in parallel for survivors only. |
| `fetch_data.py` | +44 | Every fetch function now accepts optional per-merchant credentials, falling back to `.env`. New `verify_credentials()` for fail-fast connection checks. |
| `requirements.txt` | ±1 | `google-genai` → `openai>=1.50.0`. |
| `accounts.py` | new · 34 | In-memory credential store keyed by random token. Never touches disk, never enters the cookie. Includes key masking for display. |
| `rate_limiter.py` | new · 45 | Thread-safe sliding-window limiter, one shared instance across both LLM call sites. |
| `report_store.py` | new · 24 | Read-once per-session report handoff enabling POST/redirect/GET. |
| `templates/base.html` | new · 735 | Shared shell: design tokens, full component library, top bar, animation keyframes, counter script, and named blocks for the pages to fill. |
| `templates/reconcile.html` | new · 407 | The dashboard — upload zone, summary counters, matched list, flag cards, review controls. |
| `templates/landing.html` | new · 42 | Hero, connect call-to-action, and a demo escape hatch for visitors without keys. |
| `templates/connect.html` | new · 70 | Credential form with inline error rendering and key preservation on failure. |
| `templates/index.html` | −470 | Deleted; superseded by the four templates above. |

---

## 7. Problems hit, and how they were solved

Thirteen entries, each traceable to a specific fix in the source. Tagged **[BLOCKER]** where work could not continue, **[RELIABILITY]** where it worked but would break under load or on camera, and **[CORRECTNESS]** for wrong-but-quiet behaviour.

### 7.1 — Failed payments manufacturing false flags `[CORRECTNESS]`
- **Symptom:** Live pulls returned every payment regardless of status. Failed and merely-authorised payments can never appear in a settlement, so each one produced a `PAYMENT_NOT_SETTLED` flag that was pure noise.
- **Diagnosis:** Reconciliation is only meaningful for money that actually moved.
- **Fix:** `captured_only=True` filtering in `fetch_payments()`, with the count recomputed after filtering so reported totals stay truthful. Committed as `44b0ac4` — the one fix important enough to get its own commit.

### 7.2 — Gemini free tier hit a hard daily ceiling `[BLOCKER]`
- **Symptom:** Iteration stopped. The free tier enforced both a per-minute limit and a 20-requests-per-day hard cap — and a single report with six flags spends six requests, so three test runs exhausted the day.
- **Diagnosis:** Recorded verbatim in `config.py`: *"hit both a per-minute AND a 20-per-day hard cap — unworkable for iterating on a demo."*
- **Fix:** Migrated the entire AI layer to OpenAI on paid credit. Swapped the dependency, both clients, both call shapes (`generate_content` → `chat.completions.create`), both response accessors (`.text` → `.choices[0].message.content`), and every config name and log string. The fallback contract was untouched, which is why the swap was safe to make under deadline.

### 7.3 — Sequential explanation calls made reports crawl `[RELIABILITY]`
- **Symptom:** Explanations were generated one flag at a time. Latency scaled linearly with flag count, so a larger upload meant a visibly stalled dashboard.
- **Fix:** Both call sites moved to `ThreadPoolExecutor.map`, pool sized `min(work, OPENAI_MAX_CONCURRENT_CALLS)` so small reports don't spin up idle threads. `fuzzy_match.py` needed restructuring rather than a drop-in change: scoring and LLM phrasing were interleaved in one loop, so the loop was split into a collect-candidates pass and a parallel-reasoning pass.
- **Guard:** Concurrency capped at 8, configurable — one thread per flag is fine for six flags and reckless for six hundred.

### 7.4 — Parallelism reintroduced the 429 risk it was meant to escape `[RELIABILITY]`
- **Symptom:** Eight simultaneous calls can breach a per-minute quota just as easily as a free tier can — paid limits are higher, not absent.
- **Diagnosis:** Retrying after a 429 is the wrong shape of fix: with only one retry configured, a rejected call burns its entire allowance on a request that was doomed before it left.
- **Fix:** Purpose-built `rate_limiter.py` — a lock-guarded `deque` of call timestamps over a 60-second sliding window. Excess callers block until the oldest timestamp ages out, computing the exact wait rather than polling. One shared instance is imported by both call sites, so the quota is global to the process, not per-module.
- **Ordering:** Deliberate and load-bearing: `acquire()` runs *before* the timeout executor is created. Queue time therefore never counts against the 8-second call budget.

### 7.5 — SDK timeout parameters proved unreliable `[RELIABILITY]`
- **Symptom:** The SDK's own timeout argument didn't hold consistently across versions, leaving requests able to hang past any useful demo window.
- **Fix:** Timeouts enforced client-side instead: each call is submitted to a single-worker executor and awaited with `future.result(timeout=…)`. This was written for Gemini and survived the OpenAI migration unchanged — the comment was simply reworded from "isn't reliable on every SDK version" to "enforced client-side regardless of SDK defaults."

### 7.6 — A model failure would have shown a broken dashboard on stage `[RELIABILITY]`
- **Symptom:** Any timeout, malformed JSON, or missing key would leave an explanation field blank or raise mid-render — during a judged live demo.
- **Fix:** A three-layer contract. Hand-written explanation and action text for all six flag types in `config.py`, plus a generic default. Response validation that treats incomplete JSON as a failure and retries. And an `explanation_source` field of `"ai"` or `"fallback"` carried through to the template, which relabels the heading accordingly.
- **Why it matters:** The app degrades honestly rather than pretending. Fuzzy matching got the same treatment — a failed reasoning call falls back to a sentence assembled from the deterministic `reasons` list, which is genuinely informative on its own.

### 7.7 — Refreshing after a run re-submitted the form `[CORRECTNESS]`
- **Symptom:** `/upload` and `/demo` rendered the dashboard directly from the POST. Refreshing triggered the browser's resubmit prompt and re-ran the whole reconciliation — including a fresh round of paid API calls.
- **Fix:** POST/redirect/GET. Both routes now stash the finished report in `report_store` against the visitor's session ID and redirect to `GET /reconcile`.
- **Subtlety:** A plain cache would have broken a stated design rule — that the dashboard starts empty every time and nothing on screen is pre-baked. So `pop()` is read-once: the first GET after a run consumes the report and clears it, and any later revisit returns to the empty state instead of quietly resurfacing a stale run.

### 7.8 — Confirm/dismiss decisions were lost on every re-run `[CORRECTNESS]`
- **Symptom:** Review decisions keyed to anything positional or incidental would detach the moment reconciliation ran again.
- **Fix:** Flag IDs are a truncated SHA-1 of the flag type joined with its identifying fields — `ORPHAN_ORDER|ord_1004`, for instance. The same underlying discrepancy always hashes to the same ID, so decisions in `flag_status.json` reattach across runs. `POSSIBLE_MATCH` uses the order and payment pair for the same reason.
- **Evidence:** The committed `flag_status.json` holds decisions against stable IDs that survived the intervening re-runs — including `b6e6d3b815`, a fuzzy-match ID generated after the file was first written.

### 7.9 — Razorpay OAuth needs partner approval that wouldn't arrive in time `[BLOCKER]`
- **Symptom:** Letting arbitrary merchants connect their accounts properly means OAuth, and Razorpay gates OAuth behind Technology Partner approval — *"not something a submission deadline can wait on,"* as the route docstring puts it.
- **Fix:** A key-based connect flow standing in for OAuth, designed so the security story still holds. Credentials are verified on entry, kept in a process-local store keyed by `secrets.token_urlsafe(24)`, and never written to disk. The signed session cookie carries only that token — never the secret itself, which matters because Flask cookies are signed but not encrypted. The Key ID is masked wherever it is displayed.
- **Honesty:** Both `accounts.py` and the route document this as a deliberate stand-in and name what production would need: OAuth, and a real store such as Redis with encryption at rest.

### 7.10 — Bad credentials were accepted silently `[CORRECTNESS]`
- **Symptom:** Nothing validated the key pair at connect time, so a typo was stored happily and only surfaced later as an opaque failure during an actual reconciliation.
- **Fix:** `verify_credentials()` issues the cheapest possible authenticated request — `payment.all({"count": 1})` — and lets the exception propagate. The connect form renders the reason inline and preserves the entered Key ID so only the secret needs retyping. Empty-field validation happens before any network call.

### 7.11 — The connectivity check under-reported real volume `[CORRECTNESS]`
- **Symptom:** `/razorpay/live-check` requested `count=5` and displayed the result as a total. A merchant with 200 payments was told they had 5.
- **Fix:** Raised to Razorpay's per-request maximum of 100, named as a constant rather than left as a literal. Because 100 is itself a ceiling, the response also returns `payments_count_capped` and `settlements_count_capped` booleans — so a genuine 100-plus account is flagged as capped instead of silently truncated.

### 7.12 — A live API failure could kill the demo outright `[RELIABILITY]`
- **Symptom:** Ticking "use live data" against an account that errors, or simply has no settlements yet, would leave the run with nothing to reconcile.
- **Fix:** A `mock_fallback` path. On failure or empty results, reconciliation still runs — against the demo fixtures — and the returned status object carries `source` and a human-readable `note` that the dashboard renders as a visible banner. Live results are written to separate `live_*.json` files, so a bad live pull can never overwrite the fixtures the fallback depends on.

### 7.13 — Duplicate files and a stale package layout `[CORRECTNESS]`
- **Symptom:** An abandoned `src/` directory and duplicated modules left genuine ambiguity about which copy of a file was actually being imported.
- **Fix:** Flattened to a single top-level module set and committed as `9ec44ae`, immediately before the UI overhaul — cleaning the tree first so the large refactor landed against an unambiguous baseline.

---

## 8. Evidence base

**Used as evidence:**
- Four commits on `master`, 30 Aug – 1 Sep 2026
- `git diff HEAD` — 284 insertions, 570 deletions, 8 files
- Nine untracked new files
- All 12 Python modules and 4 templates, read in full
- Explanatory code comments recording rationale
- `requirements.txt`, `.gitignore`, `.env` key names
- `data/flag_status.json` decision history
- `cpython-314` bytecode confirming the interpreter version

**Not available:**
- Chat transcripts from earlier sessions — this session started fresh
- Application logs; the app prints to stdout and writes no log file
- Razorpay or OpenAI API response logs
- Exact error text and stack traces as originally seen
- Timing of individual changes within a commit

The §7 entries are grounded in code that exists and comments that state their own reasoning. Where a symptom is described in more detail than a comment provides — the resubmit prompt in 7.7, the false-positive mechanism in 7.1 — that detail is inferred from what the fix necessarily implies, not from a retained log.

---

## 9. Known gaps

Documented in the source as prototype decisions, not oversights.

| Area | Current | Production would need |
|---|---|---|
| Account connection | Key ID / secret pasted into a form | Razorpay OAuth, pending Technology Partner approval |
| Credential storage | Process-local dict; lost on restart | Redis or equivalent, encrypted at rest |
| Flag decisions | Single JSON file, global across users | Table of `flag_id · status · updated_at · updated_by` |
| Deployment | Single instance assumed throughout | Shared state before any horizontal scaling |
| API pagination | Capped at 100 per request, reported honestly | Cursor pagination across the full payment history |
| Server | Flask development server | Production WSGI server behind a reverse proxy |
| Tests | None; scoring and reconciliation are written to be testable | Unit coverage on `_score_candidate` and the six rules |

Worth noting what the prototype shortcuts did *not* compromise: API secrets never reach the cookie or the disk, uploaded filenames are sanitised, flag statuses are validated server-side, and the AI layer cannot take the dashboard down. The gaps are in scale and durability, not in the security or correctness story.
