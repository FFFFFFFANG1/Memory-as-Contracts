def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Check no JSON wrapping
    stripped = text.strip()
    if (stripped.startswith('{') and stripped.endswith('}')) or (stripped.startswith('[') and stripped.endswith(']')):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'response appears JSON-wrapped', 'evidence_refs': []}
    if '```json' in text.lower() or stripped.startswith('```'):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'response wrapped in code fence/JSON', 'evidence_refs': []}
    # Check bullet-point list
    lines = [l for l in text.splitlines() if l.strip()]
    bullet_re = re.compile(r'^\s*([-*•+]|\d+[.)])\s+')
    bullet_lines = [l for l in lines if bullet_re.match(l)]
    if len(bullet_lines) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'not a bullet-point list', 'evidence_refs': []}
    # Check no closing remarks: last non-empty line should be a bullet
    if not bullet_re.match(lines[-1]):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'closing remark after bullets detected', 'evidence_refs': [lines[-1][:120]]}
    # Optional: bullets mention seat counts (digits)
    has_digits = any(re.search(r'\d', l) for l in bullet_lines)
    if not has_digits:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'bullets lack seat counts', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'bullet list with seat counts, no JSON, no closing remarks', 'evidence_refs': []}
