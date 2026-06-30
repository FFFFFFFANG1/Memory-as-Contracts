def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    # Check for JSON wrapper
    if (text.startswith('{') and text.endswith('}')) or (text.startswith('[') and text.endswith(']')):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'final response is JSON-wrapped', 'evidence_refs': [text[:80]]}
    # Check for key-value patterns like 'Key: value' on dedicated lines or multiple such pairs
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    kv_pattern = re.compile(r'^[\-\*]?\s*["\']?[A-Za-z_][A-Za-z0-9 _\-]*["\']?\s*[:=]\s*\S+')
    kv_lines = [l for l in lines if kv_pattern.match(l)]
    if len(lines) > 1 and len(kv_lines) >= 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'structured key-value envelope detected', 'evidence_refs': kv_lines[:3]}
    # Check for code fences containing structured data
    if '```' in text and re.search(r'```(?:json|yaml)?\s*[\{\[]', text):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'code fence with structured data', 'evidence_refs': []}
    # Should be a single sentence ideally; allow prose
    # Count sentences roughly
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s for s in sentences if s.strip()]
    if len(sentences) == 1:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'single prose sentence with no structured wrapper', 'evidence_refs': [text[:120]]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'prose response without structured envelope', 'evidence_refs': [text[:120]]}
