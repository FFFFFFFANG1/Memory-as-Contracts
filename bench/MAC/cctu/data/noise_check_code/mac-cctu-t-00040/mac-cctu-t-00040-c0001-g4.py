def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    n = len(calls)
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    lines = [l for l in final.splitlines() if l.strip()]
    bullet_lines = [l for l in lines if re.match(r'^\s*[-*•]\s+', l)]
    is_bulleted = len(bullet_lines) >= 2 and len(bullet_lines) >= max(1, len(lines) - 1)
    count_ok = (n == 5)
    if count_ok and is_bulleted:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'{n} tool calls and bulleted final answer', 'evidence_refs': []}
    reasons = []
    if not count_ok:
        reasons.append(f'tool_calls={n}, expected 5')
    if not is_bulleted:
        reasons.append('final answer not a bulleted list')
    return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
