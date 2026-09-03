"""
Holds the last reconciliation result per browser session, in memory. Kept
separate from accounts.py (which only exists once a Razorpay account is
connected) because running a reconciliation - via CSV upload or the demo
dataset - never requires a connected account.

This lets /upload and /demo redirect to GET /reconcile (POST/redirect/GET)
instead of rendering the result directly, so refreshing right after a run
never re-submits the form. The dashboard should otherwise always start
empty ("nothing on screen is pre-baked") - so pop() is read-once: the very
next GET /reconcile after a run consumes and clears it, meaning a later
revisit or refresh goes back to the empty state instead of silently
resurfacing an old result.
"""

_STORE = {}


def save(sid, report=None, error=None, razorpay_status=None):
    _STORE[sid] = {"report": report, "error": error, "razorpay_status": razorpay_status}


def pop(sid):
    return _STORE.pop(sid, None) or {"report": None, "error": None, "razorpay_status": None}
