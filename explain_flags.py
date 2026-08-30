import json
import concurrent.futures
from google import genai

import config

client = genai.Client(api_key=config.GEMINI_API_KEY) if config.GEMINI_API_KEY else None


def _call_gemini(prompt):
    """Single, un-retried call to Gemini. Raises on failure/timeout."""
    if client is None:
        raise RuntimeError("GEMINI_API_KEY not configured")

    def _do_call():
        return client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt
        )

    # Thread-based timeout: generate_content's own timeout kwarg isn't
    # reliable on every SDK version, so we enforce it ourselves.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_do_call)
        return future.result(timeout=config.GEMINI_TIMEOUT_SECONDS)


def get_explanation(flag):
    """
    Try Gemini up to GEMINI_MAX_RETRIES+1 times. On any failure/timeout,
    fall back to a hand-written explanation so the dashboard never shows
    a broken or blank message during a live demo.
    """
    prompt = f"""
You are a helpful finance assistant for a merchant using Razorpay.
A reconciliation engine has flagged the following discrepancy:

Type: {flag['type']}
Message: {flag['message']}

Explain in plain English what likely happened (2-3 sentences),
and give one clear recommended action for the finance team.
Keep it friendly and concise. Respond with ONLY a JSON object,
no markdown fences, with keys "explanation" and "action".
"""
    last_error = None
    for attempt in range(config.GEMINI_MAX_RETRIES + 1):
        try:
            response = _call_gemini(prompt)
            raw = response.text.strip().replace("```json", "").replace("```", "").strip()
            data = json.loads(raw)
            explanation = data.get("explanation", "").strip()
            action = data.get("action", "").strip()
            if explanation and action:
                return explanation, action, "ai"
            raise ValueError("Gemini returned incomplete JSON")
        except Exception as e:
            last_error = e
            continue

    # All attempts failed -> graceful fallback, never a raw error on screen
    fallback = config.FALLBACK_EXPLANATIONS.get(flag['type'], config.DEFAULT_FALLBACK)
    print(f"[explain_flags] Gemini failed for flag {flag['type']} after "
          f"{config.GEMINI_MAX_RETRIES + 1} attempt(s): {last_error}")
    return fallback["explanation"], fallback["action"], "fallback"


def enhance_report(report):
    """Add AI (or fallback) explanations to each flag and return enhanced report."""
    enhanced_flags = []
    for flag in report['flags']:
        explanation, action, source = get_explanation(flag)
        flag['ai_explanation'] = explanation
        flag['ai_action'] = action
        flag['explanation_source'] = source  # "ai" or "fallback" - useful for debugging/demo transparency
        enhanced_flags.append(flag)
    return {'matched': report['matched'], 'flags': enhanced_flags}


if __name__ == "__main__":
    with open(config.RAW_REPORT_FILE, 'r') as f:
        report = json.load(f)
    enhanced = enhance_report(report)
    with open(config.ENHANCED_REPORT_FILE, 'w') as f:
        json.dump(enhanced, f, indent=2)
    print(f"Enhanced report saved to {config.ENHANCED_REPORT_FILE}")
