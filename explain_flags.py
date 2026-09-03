import json
import concurrent.futures
from openai import OpenAI

import config
from rate_limiter import llm_limiter

client = OpenAI(api_key=config.OPENAI_API_KEY) if config.OPENAI_API_KEY else None


def _call_openai(prompt):
    """Single, un-retried call to OpenAI. Raises on failure/timeout."""
    if client is None:
        raise RuntimeError("OPENAI_API_KEY not configured")

    def _do_call():
        return client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )

    # Wait for a free slot under the shared per-minute quota BEFORE spending a
    # thread/timeout on the call - avoids firing requests that are guaranteed
    # to hit a 429 and burn a retry attempt for nothing.
    llm_limiter.acquire()

    # Thread-based timeout, enforced client-side regardless of SDK defaults.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_do_call)
        return future.result(timeout=config.OPENAI_TIMEOUT_SECONDS)


def get_explanation(flag):
    """
    Try OpenAI up to OPENAI_MAX_RETRIES+1 times. On any failure/timeout,
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
    for attempt in range(config.OPENAI_MAX_RETRIES + 1):
        try:
            response = _call_openai(prompt)
            raw = response.choices[0].message.content.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            data = json.loads(raw)
            explanation = data.get("explanation", "").strip()
            action = data.get("action", "").strip()
            if explanation and action:
                return explanation, action, "ai"
            raise ValueError("OpenAI returned incomplete JSON")
        except Exception as e:
            last_error = e
            continue

    # All attempts failed -> graceful fallback, never a raw error on screen
    fallback = config.FALLBACK_EXPLANATIONS.get(flag['type'], config.DEFAULT_FALLBACK)
    print(f"[explain_flags] OpenAI failed for flag {flag['type']} after "
          f"{config.OPENAI_MAX_RETRIES + 1} attempt(s): {last_error}")
    return fallback["explanation"], fallback["action"], "fallback"


def enhance_report(report):
    """Add AI (or fallback) explanations to each flag and return enhanced report.
    Flags that already carry an ai_explanation (e.g. POSSIBLE_MATCH suggestions
    from fuzzy_match.py, which generate their own reasoning) are left untouched -
    this only fills in explanations for the standard reconcile.py flag types.

    Runs OpenAI calls for different flags IN PARALLEL (one thread per flag, up
    to OPENAI_MAX_CONCURRENT_CALLS), not sequentially.
    """
    needs_explanation = [f for f in report['flags'] if not f.get('ai_explanation')]

    if needs_explanation:
        pool_size = min(len(needs_explanation), config.OPENAI_MAX_CONCURRENT_CALLS)
        with concurrent.futures.ThreadPoolExecutor(max_workers=pool_size) as executor:
            results = list(executor.map(get_explanation, needs_explanation))

        for flag, (explanation, action, source) in zip(needs_explanation, results):
            flag['ai_explanation'] = explanation
            flag['ai_action'] = action
            flag['explanation_source'] = source  # "ai" or "fallback" - useful for debugging/demo transparency

    return {'matched': report['matched'], 'flags': report['flags']}


if __name__ == "__main__":
    import fuzzy_match

    with open(config.RAW_REPORT_FILE, 'r') as f:
        report = json.load(f)
    enhanced = enhance_report(report)
    enhanced['flags'].extend(fuzzy_match.run_fuzzy_matching(report))
    with open(config.ENHANCED_REPORT_FILE, 'w') as f:
        json.dump(enhanced, f, indent=2)
    print(f"Enhanced report saved to {config.ENHANCED_REPORT_FILE}")
