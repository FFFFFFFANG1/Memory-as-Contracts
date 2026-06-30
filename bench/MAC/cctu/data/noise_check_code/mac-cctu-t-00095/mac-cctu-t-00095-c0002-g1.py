def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    n = len(calls)
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    if n > 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{n} tool calls exceeds max 3', 'evidence_refs': []}
    md_patterns = [r'^#', r'\*\*', r'__', r'`', r'^\s*[-*+]\s', r'\[[^\]]+\]\([^\)]+\)', r'^>\s']
    for pat in md_patterns:
        if re.search(pat, resp, re.MULTILINE):
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'markdown detected: {pat}', 'evidence_refs': []}
    lines = [l for l in resp.splitlines() if l.strip()]
    if len(lines) != 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'expected single line, got {len(lines)}', 'evidence_refs': []}
    if not re.search(r'\d', lines[0]):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no numeric revenue figure present', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'{n} tool calls; single plain-text line with figure', 'evidence_refs': []}
