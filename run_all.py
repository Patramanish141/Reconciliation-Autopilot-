import subprocess
import sys


def run_command(cmd):
    print(f"\nRunning: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode != 0:
        sys.exit(f"Command failed: {' '.join(cmd)}")
    return result


if __name__ == "__main__":
    run_command([sys.executable, "create_mock_data.py"])
    run_command([sys.executable, "reconcile.py"])
    run_command([sys.executable, "explain_flags.py"])

    print("\nPipeline complete. Starting dashboard...\n")
    # app.py runs the Flask dev server directly (not captured, so logs stream live)
    subprocess.run([sys.executable, "app.py"])
