"""
Fuzzy-matching layer: runs AFTER reconcile.py's exact-match pass.

Scope (deliberately narrow): only looks at orders/payments that already
FAILED exact matching (ORPHAN_ORDER / PAYMENT_WITHOUT_ORDER flags). It never
touches or overrides an exact match - that logic in reconcile.py is untouched.

Design: candidate scoring (amount/email/date proximity) is deterministic and
testable without any API calls. Gemini is used only to phrase the plain-English
reasoning for a candidate - same fallback-safe pattern as explain_flags.py, so
a Gemini failure degrades to a template sentence, never a crash or blank field.
"""
import concurrent.futures
import hashlib
import json
import csv
from datetime import datetime, timezone
from google import genai

import config

client = genai.Client(api_key=config.GEMINI_API_KEY) if config.GEMINI_API_KEY else None

CONFIDENCE_THRESHOLD = 0.5  # below this, don't suggest a match at all


def _order_date_to_ts(date_str):
    """merchant CSV dates are 'YYYY-MM-DD' - convert to a unix timestamp for comparison."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def _score_candidate(order, payment):
    """
    Deterministic 0.0-1.0 confidence score for whether `order` (merchant CSV row)
    and `payment` (Razorpay transaction) are actually the same transaction,
    despite not matching on order_id.
    """
    score = 0.0
    reasons = []

    order_amount = int(order['amount'])
    payment_amount = payment['amount']
    if order_amount == payment_amount:
        score += 0.5
        reasons.append("exact amount match")
    elif abs(order_amount - payment_amount) / max(order_amount, 1) < 0.01:
        score += 0.3
        reasons.append("amount matches within 1%")

    order_email = (order.get('email') or '').strip().lower()
    payment_email = (payment.get('email') or '').strip().lower()
    if order_email and payment_email and order_email == payment_email:
        score += 0.3
        reasons.append("exact email match")

    order_ts = _order_date_to_ts(order.get('order_date'))
    payment_ts = payment.get('created_at')
    if order_ts and payment_ts:
        days_apart = abs(order_ts - payment_ts) / 86400
        if days_apart <= 1:
            score += 0.2
            reasons.append("same-day timestamp")
        elif days_apart <= 3:
            score += 0.1
            reasons.append("timestamps within 3 days")

    return min(score, 1.0), reasons


def _gemini_reasoning(order, payment, reasons):
    """Ask Gemini to phrase the match reasoning in plain English. Falls back to a
    template sentence built from `reasons` if Gemini fails/times out."""
    fallback = (
        f"Order {order['order_id']} and payment {payment['id']} were not linked by ID, "
        f"but likely match based on: {', '.join(reasons)}. Please verify manually before confirming."
    )
    if client is None:
        return fallback, "fallback"

    prompt = f"""
A reconciliation engine found an order and a payment that don't share the same
order_id, but look like they might be the same transaction based on: {', '.join(reasons)}.

Order: {order['order_id']}, amount Rs.{int(order['amount'])/100:.2f}, email {order.get('email')}
Payment: {payment['id']}, amount Rs.{payment['amount']/100:.2f}, email {payment.get('email')}

Write ONE plain-English sentence (max 30 words) explaining why these likely match
and telling the finance team what to verify before confirming. No JSON, just the sentence.
"""

    def _do_call():
        return client.models.generate_content(model=config.GEMINI_MODEL, contents=prompt)

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_call)
            response = future.result(timeout=config.GEMINI_TIMEOUT_SECONDS)
        text = response.text.strip()
        if text:
            return text, "ai"
        return fallback, "fallback"
    except Exception:
        return fallback, "fallback"


def find_fuzzy_matches(orphan_orders, unmatched_payments):
    """
    orphan_orders: list of merchant CSV order dicts (order_id, amount, email, order_date)
                   that had NO exact-match payment.
    unmatched_payments: list of Razorpay payment dicts (id, amount, email, created_at, order_id)
                         that had NO matching merchant order.

    Returns a list of suggestion dicts (type='POSSIBLE_MATCH'), one per candidate
    pair scoring above CONFIDENCE_THRESHOLD. Each order/payment is only suggested
    once, matched to its single best candidate (no duplicate suggestions).
    """
    suggestions = []
    used_payment_ids = set()

    for order in orphan_orders:
        best_score, best_payment, best_reasons = 0.0, None, []

        for payment in unmatched_payments:
            if payment['id'] in used_payment_ids:
                continue
            score, reasons = _score_candidate(order, payment)
            if score > best_score:
                best_score, best_payment, best_reasons = score, payment, reasons

        if best_payment and best_score >= CONFIDENCE_THRESHOLD:
            used_payment_ids.add(best_payment['id'])
            reasoning, source = _gemini_reasoning(order, best_payment, best_reasons)

            flag_id = hashlib.sha1(
                f"POSSIBLE_MATCH|{order['order_id']}|{best_payment['id']}".encode()
            ).hexdigest()[:10]

            suggestions.append({
                'id': flag_id,
                'type': 'POSSIBLE_MATCH',
                'order_id': order['order_id'],
                'transaction_id': best_payment['id'],
                'confidence': round(best_score, 2),
                'message': (
                    f"Order {order['order_id']} and payment {best_payment['id']} don't share an "
                    f"ID, but scored {round(best_score * 100)}% likely to be the same transaction."
                ),
                'ai_explanation': reasoning,
                'ai_action': "Review both records and confirm or dismiss this suggested match.",
                'explanation_source': source,
            })

    return suggestions


def run_fuzzy_matching(results, transactions_file=None, orders_file=None):
    """
    Wrapper: takes the output of reconcile.run_reconciliation() (unchanged),
    reloads the raw order/payment records for whichever ones got flagged as
    ORPHAN_ORDER / PAYMENT_WITHOUT_ORDER, and returns fuzzy-match suggestions.

    Does not modify `results` or reconcile.py's logic in any way - purely additive.
    """
    transactions_file = transactions_file or config.TRANSACTIONS_FILE
    orders_file = orders_file or config.ORDERS_FILE

    orphan_order_ids = {
        f['order_id'] for f in results['flags'] if f['type'] == 'ORPHAN_ORDER'
    }
    unmatched_payment_ids = {
        f['transaction_id'] for f in results['flags'] if f['type'] == 'PAYMENT_WITHOUT_ORDER'
    }

    if not orphan_order_ids or not unmatched_payment_ids:
        return []  # nothing to fuzzy-match against

    with open(orders_file, 'r') as f:
        all_orders = list(csv.DictReader(f))
    orphan_orders = [o for o in all_orders if o['order_id'] in orphan_order_ids]

    with open(transactions_file, 'r') as f:
        all_payments = json.load(f).get('items', [])
    unmatched_payments = [p for p in all_payments if p['id'] in unmatched_payment_ids]

    return find_fuzzy_matches(orphan_orders, unmatched_payments)
