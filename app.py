import os
import uuid
from flask import Flask, render_template, request, redirect, jsonify, session

from reconcile import run_reconciliation
from explain_flags import enhance_report
import flag_status
import fetch_data
import fuzzy_match
import accounts
import report_store
import config

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.secret_key = config.SECRET_KEY


@app.before_request
def _ensure_sid():
    """Every visitor (connected or not) gets a stable per-browser session id,
    used to look up their last reconciliation result in report_store."""
    if 'sid' not in session:
        session['sid'] = uuid.uuid4().hex


def _connected_account():
    """Returns {'key_id', 'key_secret'} for the merchant connected in this
    browser session, or None if nobody's connected (caller falls back to the
    app owner's .env credentials)."""
    return accounts.get_credentials(session.get('rzp_token'))


def _active_credentials():
    """(key_id, key_secret) to use for live Razorpay calls: the connected
    merchant's own credentials if present, else the app owner's .env keys."""
    account = _connected_account()
    if account:
        return account['key_id'], account['key_secret']
    return config.RAZORPAY_KEY_ID, config.RAZORPAY_KEY_SECRET


def _connected_key_id():
    account = _connected_account()
    return accounts.mask_key_id(account['key_id']) if account else None


def _build_report(orders_file, transactions_file=None, settlements_file=None):
    """Shared logic: run reconciliation + fuzzy match + AI explanations for a given
    orders_file (and optionally live-fetched transactions/settlements files)."""
    results = run_reconciliation(
        orders_file=orders_file,
        transactions_file=transactions_file,
        settlements_file=settlements_file,
    )
    report = enhance_report(results)
    report['flags'].extend(
        fuzzy_match.run_fuzzy_matching(
            results, transactions_file=transactions_file, orders_file=orders_file
        )
    )
    return report


@app.route('/', methods=['GET'])
def landing():
    """
    Root page: just the 'Connect with Razorpay' entry point. If this browser
    session already has a connected account, skip straight to the dashboard.
    """
    if _connected_account():
        return redirect('/reconcile')
    return render_template('landing.html')


@app.route('/connect', methods=['GET'])
def connect_form():
    """Page 2: enter Key ID / Key Secret. Already-connected visitors are sent
    straight to the dashboard instead of being asked again."""
    if _connected_account():
        return redirect('/reconcile')
    return render_template('connect.html', error=None, key_id=None)


@app.route('/connect', methods=['POST'])
def connect_account():
    """
    Merchant-facing 'login': paste your own Razorpay Key ID + Key Secret once,
    we verify it works, then keep it server-side (in-memory, see accounts.py)
    for the rest of this browser session so every later live-data action just
    works without asking again. This is the practical stand-in for full
    Razorpay OAuth (see accounts.py docstring) - OAuth needs Technology Partner
    approval which isn't something a submission deadline can wait on.
    """
    key_id = (request.form.get('key_id') or '').strip()
    key_secret = (request.form.get('key_secret') or '').strip()

    if not key_id or not key_secret:
        return render_template(
            'connect.html', error="Enter both your Key ID and Key Secret.", key_id=key_id,
        )

    try:
        fetch_data.verify_credentials(key_id, key_secret)
    except Exception as e:
        return render_template(
            'connect.html', error=f"Could not connect: {e}", key_id=key_id,
        )

    token = accounts.create_session(key_id, key_secret)
    session['rzp_token'] = token
    return redirect('/reconcile')


@app.route('/disconnect', methods=['POST'])
def disconnect_account():
    accounts.clear_session(session.get('rzp_token'))
    session.pop('rzp_token', None)
    return redirect('/')


@app.route('/reconcile', methods=['GET'])
def reconcile_dashboard():
    """
    Page 3: the actual reconciliation dashboard. Reachable whether or not a
    Razorpay account is connected - CSV upload and the demo dataset never
    needed live credentials, only the 'use live data' path does.

    Shows a result only immediately after /upload or /demo redirects here -
    report_store.pop() consumes it, so a later revisit or refresh goes back
    to the empty state rather than resurfacing a stale run (the dashboard is
    meant to start empty until you explicitly act, every time).
    """
    state = report_store.pop(session['sid'])
    report = state['report']
    if report:
        flag_status.apply_statuses(report['flags'])
    return render_template(
        'reconcile.html', report=report, error=state['error'],
        razorpay_status=state['razorpay_status'], connected_key_id=_connected_key_id(),
    )


@app.route('/upload', methods=['POST'])
def upload_and_reconcile():
    report = None
    error = None
    razorpay_status = None

    if 'csv_file' not in request.files:
        return redirect('/reconcile')
    file = request.files['csv_file']
    if file.filename == '':
        return redirect('/reconcile')
    if not file.filename.endswith('.csv'):
        return "Please upload a CSV file.", 400

    from werkzeug.utils import secure_filename
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    use_live = request.form.get('use_live_data') == 'on'
    key_id, key_secret = _active_credentials()

    try:
        if use_live:
            fetch_status = fetch_data.fetch_and_save_live_data(key_id=key_id, key_secret=key_secret)
            razorpay_status = fetch_status
            if fetch_status['source'] == 'mock_fallback':
                # Live account had nothing usable - still reconcile, but be honest about it
                report = _build_report(orders_file=filepath)
            else:
                report = _build_report(
                    orders_file=filepath,
                    transactions_file=config.LIVE_TRANSACTIONS_FILE,
                    settlements_file=config.LIVE_SETTLEMENTS_FILE,
                )
        else:
            report = _build_report(orders_file=filepath)
    except Exception as e:
        error = f"Could not process this file: {e}"

    if report:
        flag_status.apply_statuses(report['flags'])

    report_store.save(session['sid'], report=report, error=error, razorpay_status=razorpay_status)
    return redirect('/reconcile')


@app.route('/demo', methods=['POST'])
def load_demo():
    """Explicit, clearly-labeled demo path: runs the curated mock dataset
    (create_mock_data.py's output) so the specific discrepancy types are
    reliably reproducible on camera. Only runs when the button is clicked."""
    import create_mock_data
    create_mock_data.main()

    report = _build_report(orders_file=config.ORDERS_FILE)
    flag_status.apply_statuses(report['flags'])

    report_store.save(session['sid'], report=report, error=None, razorpay_status=None)
    return redirect('/reconcile')


@app.route('/flag/<flag_id>/status', methods=['POST'])
def update_flag_status(flag_id):
    """Human-in-the-loop: confirm or dismiss a flag. Called via fetch() from the dashboard."""
    new_status = request.form.get('status')
    try:
        flag_status.set_status(flag_id, new_status)
        return jsonify({"ok": True, "flag_id": flag_id, "status": new_status})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route('/razorpay/live-check', methods=['GET'])
def razorpay_live_check():
    """
    Proves real Razorpay API connectivity. Separate from reconciliation itself -
    this is a quick sanity check; the actual live-data reconciliation happens
    via the 'use_live_data' checkbox on the upload form (see /upload).

    Fetches up to Razorpay's per-request max (100) so the count reflects your
    actual total, not an arbitrary sample size. If you genuinely have 100+
    payments, this flags that explicitly rather than silently under-reporting.
    """
    RAZORPAY_MAX_PER_REQUEST = 100
    key_id, key_secret = _active_credentials()
    try:
        payments = fetch_data.fetch_payments(count=RAZORPAY_MAX_PER_REQUEST, key_id=key_id, key_secret=key_secret)
        settlements = fetch_data.fetch_settlements(count=RAZORPAY_MAX_PER_REQUEST, key_id=key_id, key_secret=key_secret)
        return jsonify({
            "ok": True,
            "connected": True,
            "payments_count": payments.get("count", 0),
            "payments_count_capped": payments.get("count", 0) >= RAZORPAY_MAX_PER_REQUEST,
            "settlements_count": settlements.get("count", 0),
            "settlements_count_capped": settlements.get("count", 0) >= RAZORPAY_MAX_PER_REQUEST,
            "sample_payments": payments.get("items", [])[:3],
            "sample_settlements": settlements.get("items", [])[:3],
        })
    except Exception as e:
        return jsonify({"ok": False, "connected": False, "error": str(e)}), 200


if __name__ == '__main__':
    debug_mode = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    app.run(debug=debug_mode)
