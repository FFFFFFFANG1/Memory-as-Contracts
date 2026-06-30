def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    used = any((c.get('name')=='historical_event_locator') for c in calls)
    if not used:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'historical_event_locator not used in trajectory', 'evidence_refs': []}
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    lines = [l.rstrip() for l in resp.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^\s*\d+[\.\)]\s+\S', l)]
    has_numbered = len(numbered) >= 1 and len(numbered) >= max(1, len(lines)-2)
    # Look at last non-empty line for URL in parentheses
    tail = resp.rstrip()
    ends_with_url_parens = bool(re.search(r'\((?:https?://|www\.)[^\s()]+\)\s*$', tail))
    followed = has_numbered and ends_with_url_parens
    reason = f'numbered_lines={len(numbered)}/{len(lines)}, ends_with_url_parens={ends_with_url_parens}'
    return {'observed_followed': bool(followed), 'confidence': 'high' if (has_numbered or ends_with_url_parens) else 'medium', 'reason': reason, 'evidence_refs': []}
