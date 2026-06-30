def evaluate(trace):
    import re, json
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Try JSON parse
    try:
        parsed = json.loads(resp)
        if isinstance(parsed, (dict, list)):
            return {'observed_followed': False, 'confidence': 'high', 'reason': 'response parsed as JSON object/array', 'evidence_refs': [resp[:120]]}
    except Exception:
        pass
    # Check for JSON-like wrapper or key-value structure
    if (resp.startswith('{') and resp.endswith('}')) or (resp.startswith('[') and resp.endswith(']')):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'response wrapped in JSON-like braces/brackets', 'evidence_refs': [resp[:120]]}
    # Detect key: value structured formatting on multiple lines
    lines = [l for l in resp.splitlines() if l.strip()]
    kv_pattern = re.compile(r'^\s*["\']?[A-Za-z_][A-Za-z0-9_ ]*["\']?\s*:\s*.+')
    kv_lines = [l for l in lines if kv_pattern.match(l)]
    if len(lines) > 1 and len(kv_lines) >= 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'multiple key:value styled lines suggest structured formatting', 'evidence_refs': kv_lines[:3]}
    # Should be a single sentence-ish plain text
    # Count sentence terminators
    if len(lines) > 3:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'response has many lines, not a single sentence', 'evidence_refs': [resp[:120]]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'plain text sentence without JSON or key-value structure', 'evidence_refs': [resp[:120]]}
