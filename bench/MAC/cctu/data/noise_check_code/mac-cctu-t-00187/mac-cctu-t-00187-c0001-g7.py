def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {"observed_followed": None, "confidence": "unknown", "reason": "empty final response", "evidence_refs": []}
    # Check for JSON wrapping
    stripped = text.lstrip('` \n')
    if stripped.startswith('{') or stripped.startswith('['):
        try:
            import json
            json.loads(re.sub(r'^```(?:json)?|```$', '', text.strip(), flags=re.M).strip())
            return {"observed_followed": False, "confidence": "high", "reason": "final response is JSON", "evidence_refs": []}
        except Exception:
            pass
    # Check for tabular markdown (pipe table)
    lines = text.splitlines()
    pipe_lines = [l for l in lines if l.count('|') >= 2]
    if len(pipe_lines) >= 2 and any(re.match(r'^\s*\|?\s*:?-{2,}', l) for l in lines):
        return {"observed_followed": False, "confidence": "high", "reason": "final response contains a markdown table", "evidence_refs": []}
    # Check bulleted list presence
    bullet_lines = [l for l in lines if re.match(r'^\s*[-*•]\s+\S', l)]
    if len(bullet_lines) < 1:
        return {"observed_followed": False, "confidence": "medium", "reason": "no bulleted items detected", "evidence_refs": []}
    return {"observed_followed": True, "confidence": "medium", "reason": "plain-text bulleted list without JSON/table wrapping", "evidence_refs": []}
