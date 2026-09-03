<div align="center">

# 🔍 Reconciliation Autopilot

### AI-powered payment reconciliation for Razorpay merchants

*Automatically match payments against settlements, catch the discrepancies humans miss, and get plain-English explanations for every one — with a human in the loop for every decision.*

<br>

![Python](https://img.shields.io/badge/Python-3.14-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white)
![Razorpay](https://img.shields.io/badge/Razorpay-API-0C2651?style=for-the-badge&logo=razorpay&logoColor=0D94FB)
![OpenAI](https://img.shields.io/badge/OpenAI-gpt--5--mini-412991?style=for-the-badge&logo=openai&logoColor=white)

<br>

*Built for the Razorpay AI Buildathon 2026 · Track 4: AI Finance Controller*

</div>

---

## The Problem

Every business on Razorpay hits the same quiet, expensive problem: **reconciliation.**

Money arrives through UPI, cards, and netbanking. Settlements land days later — sometimes with fees deducted, sometimes missing entirely, sometimes duplicated. Finance teams spend **10–20 hours every week** manually matching their own order records against Razorpay's settlement reports in a spreadsheet, hunting for the one payment that didn't settle or the ₹120 that quietly vanished as a fee.

**Reconciliation Autopilot makes that manual grind disappear.**

---

## What It Does

```
  Merchant orders (CSV)  ─┐
                          ├─→  🔍 Reconciliation Engine  ─→  ✅ Matched
  Razorpay payments  ─────┤         (6 rules + AI)          🚩 Flagged + explained
  Razorpay settlements  ──┘                                 🤝 Human confirms / dismisses
```

Connect a real Razorpay account, upload your order records, and the engine matches every payment against every settlement — flagging what doesn't line up and explaining each issue in plain English. A human reviews and confirms or dismisses every finding.

---

## Key Features

### 🔐 Connect your own Razorpay account, securely
Paste your Key ID and Secret once. Credentials are **verified live before they're accepted** — a typo fails immediately instead of causing a silent bug later. Keys are held **in server memory only, never written to disk**, and the session cookie carries only a random token — never the secret itself.

### 🧮 Seven kinds of discrepancy, caught automatically

| Flag | What it catches |
|:--|:--|
| `ORPHAN_ORDER` | Order booked, but no payment against it |
| `PAYMENT_NOT_SETTLED` | Money captured, but never paid out |
| `DUPLICATE_SETTLEMENT` | The same payment credited twice |
| `AMOUNT_MISMATCH` | Settled amount ≠ captured amount (usually fees) |
| `PAYMENT_WITHOUT_ORDER` | A payment with no matching order record |
| `UNKNOWN_SETTLEMENT_TRANSACTION` | Settlement references an untracked transaction |
| ✨ `POSSIBLE_MATCH` | **AI-assisted** — recovers orphaned records the exact rules gave up on |

### ✨ Fuzzy matching that earns the word "AI"
When an order and a payment don't share an ID, the exact rules give up. The fuzzy matcher scores them on amount, email, and date proximity — and if they line up, suggests they're the same transaction, **with a confidence score, not a blind guess.** The scoring is deterministic and testable; the AI is used only to phrase the reasoning.

### 🤝 Human-in-the-loop, always
Confirm, dismiss, or undo any flag — with live-updating counters and no page reload. Decisions are keyed to a **stable hash ID**, so re-running reconciliation on the same data never loses your review history.

### 🛡️ It fails safely
A bad API call, a slow model, an empty live account — none of it breaks the dashboard. Every AI explanation has a **hand-written fallback baked in before the API was ever wired up**, so the dashboard is *incapable* of showing a blank or broken message. It degrades honestly, every time.

---

## Tech Stack

<div align="center">

| Layer | Choice |
|:--|:--|
| **Backend** | Python 3.14 · Flask · Jinja2 |
| **Payments** | Official Razorpay Python SDK (real `payment.all()` / `settlement.all()`) |
| **AI** | OpenAI `gpt-5-mini` — explanations + fuzzy-match reasoning |
| **Reliability** | Thread-pooled parallel calls · shared rate limiter · client-side timeouts · 3-layer fallback |
| **Persistence** | JSON for flag decisions · credentials in-memory only |
| **Frontend** | Hand-written CSS + vanilla JS (nothing to compile) |

</div>

---

## Getting Started

### Prerequisites
- Python 3.14
- A Razorpay **test-mode** account (Key ID + Secret)
- An OpenAI API key

### Installation

```bash
# 1. Clone and enter the project
git clone <your-repo-url>
cd reconciliation-autopilot

# 2. Create and activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Add your keys to a .env file
```

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-your-openai-key
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_key_secret
```

### Run it

```bash
python app.py
```

Open **http://127.0.0.1:5000** — connect your account, or click **Load Demo Dataset** to see it work immediately with a curated set of planted discrepancies.

---

## How It Works

### Application routes

| Route | Method | Behaviour |
|:--|:--|:--|
| `/` | GET | Landing page; redirects to the dashboard if already connected |
| `/connect` | GET · POST | Credential form → verifies keys, mints a session token |
| `/disconnect` | POST | Drops stored credentials and the cookie token |
| `/reconcile` | GET | Dashboard; consumes any pending report exactly once |
| `/upload` | POST | Reconciles an uploaded CSV, optionally against live data |
| `/demo` | POST | Regenerates fixtures and reconciles them |
| `/flag/<id>/status` | POST | Records a confirm / dismiss / undo decision |
| `/razorpay/live-check` | GET | Connectivity probe returning counts and cap warnings |

### The reconciliation flow

1. **Ingest** — pull live payments & settlements from Razorpay (captured payments only), or load the demo fixtures
2. **Match** — six deterministic rules pair orders → payments → settlements and flag every mismatch
3. **Recover** — the fuzzy matcher takes a second pass at orphaned records the exact rules couldn't pair
4. **Explain** — the AI layer turns each raw flag into a plain-English explanation and a recommended action, in parallel
5. **Review** — a human confirms or dismisses each finding; decisions persist across re-runs

### Engineering notes worth knowing

- **Live and demo data never collide** — live results write to separate `live_*.json` files, so a failed live pull can never destroy a working demo.
- **POST/redirect/GET** on every run path, so refreshing the dashboard never re-submits the form or re-spends API calls.
- **A shared sliding-window rate limiter** sits in front of every AI call, so parallelism never trips an API quota.
- **Stable SHA-1 flag IDs** mean the same discrepancy always hashes to the same ID — review decisions reattach across reconciliation runs.

---

## Known Gaps

*Documented as deliberate prototype decisions, not oversights.*

| Area | Current | Production would need |
|:--|:--|:--|
| **Account connection** | Key ID / Secret pasted into a form | Razorpay OAuth (pending Technology Partner approval) |
| **Credential storage** | Process-local dict; lost on restart | Redis or equivalent, encrypted at rest |
| **Flag decisions** | Single JSON file | A table of `flag_id · status · updated_at · updated_by` |
| **Deployment** | Single Flask dev instance | Production WSGI server behind a reverse proxy |
| **API pagination** | Capped at 100/request, reported honestly | Cursor pagination across full payment history |
| **Tests** | None yet (core logic written to be testable) | Unit coverage on scoring and the six rules |

> **What the shortcuts did *not* compromise:** API secrets never reach the cookie or the disk, uploaded filenames are sanitised, flag statuses are validated server-side, and the AI layer cannot take the dashboard down. The gaps are in scale and durability — not in the security or correctness story.

---

<div align="center">

**Reconciliation Autopilot** — turning a 10–20 hour weekly grind into a few minutes of review.

*Built with Python, Flask, the Razorpay API, and OpenAI.*

</div>
