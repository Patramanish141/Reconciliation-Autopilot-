"""
Pulls real payment & settlement data from Razorpay's API (test mode).

Test-mode accounts often have few or zero real settlements, since a
settlement is only created after a captured payment completes its full
payout cycle. So this module tries the real API first and transparently
falls back to mock data if the account has nothing to reconcile against -
never leaves the demo showing an empty dashboard.
"""
import json
import razorpay

import config


def _get_client():
    if not config.RAZORPAY_KEY_ID or not config.RAZORPAY_KEY_SECRET:
        raise RuntimeError("RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET not configured in .env")
    return razorpay.Client(auth=(config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET))


def fetch_payments(count=50, captured_only=True):
    """
    Fetch recent payments from Razorpay. Returns the raw API response dict,
    filtered to shape {'entity': 'collection', 'count': N, 'items': [...]}.

    captured_only=True (default) drops failed/pending payments - reconciliation
    only makes sense for money that actually moved. A failed payment will never
    have a settlement, so including it would just create false-positive flags.
    """
    client = _get_client()
    result = client.payment.all({"count": count})

    if captured_only:
        items = [p for p in result.get("items", []) if p.get("status") == "captured"]
        result = {**result, "items": items, "count": len(items)}

    return result


def fetch_settlements(count=50):
    """Fetch recent settlements from Razorpay. Returns the raw API response dict."""
    client = _get_client()
    return client.settlement.all({"count": count})


def fetch_and_save_live_data():
    """
    Attempt to pull real payments + settlements from Razorpay and write them
    to config.TRANSACTIONS_FILE / config.SETTLEMENTS_FILE in the same shape
    reconcile.py already expects.

    Returns a dict describing what happened, so callers (e.g. app.py) can
    show an honest status message instead of silently mocking data.
    """
    status = {"source": "live", "payments_count": 0, "settlements_count": 0, "note": ""}

    try:
        payments = fetch_payments()
        settlements = fetch_settlements()
    except Exception as e:
        status["source"] = "mock_fallback"
        status["note"] = f"Razorpay API call failed ({e}); using mock data instead."
        return status

    status["payments_count"] = payments.get("count", 0)
    status["settlements_count"] = settlements.get("count", 0)

    if status["payments_count"] == 0 and status["settlements_count"] == 0:
        status["source"] = "mock_fallback"
        status["note"] = (
            "Connected to Razorpay successfully, but this test account has "
            "no payments/settlements yet — using mock data instead."
        )
        return status

    # Normalize into the same {"items": [...]} shape reconcile.py expects.
    with open(config.TRANSACTIONS_FILE, "w") as f:
        json.dump({"items": payments.get("items", [])}, f, indent=2)

    with open(config.SETTLEMENTS_FILE, "w") as f:
        json.dump({"items": settlements.get("items", [])}, f, indent=2)

    status["note"] = (
        f"Pulled {status['payments_count']} live payment(s) and "
        f"{status['settlements_count']} live settlement(s) from Razorpay."
    )
    return status


if __name__ == "__main__":
    result = fetch_and_save_live_data()
    print(json.dumps(result, indent=2))
