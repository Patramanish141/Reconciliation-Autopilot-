import os
import json
from flask import Flask, render_template, request, redirect, jsonify

from reconcile import run_reconciliation
from explain_flags import enhance_report
import flag_status
import fetch_data
import fuzzy_match
import config

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER


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
def dashboard():
    """
    Dashboard starts EMPTY on every load. Reconciliation only ever runs when the
    person explicitly acts - uploading a CSV, or clicking 'Load Demo Dataset'.
    No auto-loading of cached/mock results, so nothing on screen is pre-baked.
    """
    return render_template('index.html', report=None, error=None, razorpay_status=None)


@app.route('/upload', methods=['POST'])
def upload_and_reconcile():
    report = None
    error = None
    razorpay_status = None

    if 'csv_file' not in request.files:
        return redirect('/')
    file = request.files['csv_file']
    if file.filename == '':
        return redirect('/')
    if not file.filename.endswith('.csv'):
        return "Please upload a CSV file.", 400

    from werkzeug.utils import secure_filename
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    use_live = request.form.get('use_live_data') == 'on'

    try:
        if use_live:
            fetch_status = fetch_data.fetch_and_save_live_data()
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

    return render_template('index.html', report=report, error=error, razorpay_status=razorpay_status)


@app.route('/demo', methods=['POST'])
def load_demo():
    """Explicit, clearly-labeled demo path: runs the curated mock dataset
    (create_mock_data.py's output) so the specific discrepancy types are
    reliably reproducible on camera. Only runs when the button is clicked."""
    import create_mock_data
    create_mock_data.main()

    report = _build_report(orders_file=config.ORDERS_FILE)
    flag_status.apply_statuses(report['flags'])

    return render_template(
        'index.html', report=report, error=None, razorpay_status=None, is_demo=True
    )


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
    """
    try:
        payments = fetch_data.fetch_payments(count=5)
        settlements = fetch_data.fetch_settlements(count=5)
        return jsonify({
            "ok": True,
            "connected": True,
            "payments_count": payments.get("count", 0),
            "settlements_count": settlements.get("count", 0),
            "sample_payments": payments.get("items", [])[:3],
            "sample_settlements": settlements.get("items", [])[:3],
        })
    except Exception as e:
        return jsonify({"ok": False, "connected": False, "error": str(e)}), 200


if __name__ == '__main__':
    debug_mode = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    app.run(debug=debug_mode)