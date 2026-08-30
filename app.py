import os
import json
from flask import Flask, render_template, request, redirect

from reconcile import run_reconciliation
from explain_flags import enhance_report
import config

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER


@app.route('/', methods=['GET', 'POST'])
def dashboard():
    report = None
    error = None

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

    return render_template('index.html', report=report, error=error)


if __name__ == '__main__':
    app.run(debug=True)
