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


@app.route('/', methods=['GET', 'POST'])
def dashboard():
    report = None
    error = None
    razorpay_status = None

    if request.method == 'POST':
        if 'csv_file' not in request.files:
            return redirect(request.url)
        file = request.files['csv_file']
        if file.filename == '':
            return redirect(request.url)
        if file and file.filename.endswith('.csv'):
            from werkzeug.utils import secure_filename
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            try:
                results = run_reconciliation(orders_file=filepath)
                report = enhance_report(results)
                report['flags'].extend(
                    fuzzy_match.run_fuzzy_matching(results, orders_file=filepath)
                )
            except Exception as e:
                error = f"Could not process this file: {e}"
        else:
            return "Please upload a CSV file.", 400
    else:
        if os.path.exists(config.ENHANCED_REPORT_FILE):
            with open(config.ENHANCED_REPORT_FILE, 'r') as f:
                report = json.load(f)
        else:
            results = run_reconciliation()
            report = enhance_report(results)
            report['flags'].extend(fuzzy_match.run_fuzzy_matching(results))

    if report:
        flag_status.apply_statuses(report['flags'])

    return render_template('index.html', report=report, error=error, razorpay_status=razorpay_status)


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
    Proves real Razorpay API connectivity without disturbing the reconciliation
    demo dataset. Fetches live payment/settlement counts and a couple of sample
    records so the dashboard (or the pitch video) can show genuine API data.
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
