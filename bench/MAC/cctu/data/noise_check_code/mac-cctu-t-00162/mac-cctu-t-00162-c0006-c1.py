def evaluate(trace):
    import re
    allowed = {'tribal_language_identifier', 'historical_city_identifier'}
    calls = trace.get('tool_calls') or []
    used = [c.get('name') for c in calls if c.get('name')]
    if not used and not trace.get('final_response'):
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls or response found', 'evidence_refs': []}
    disallowed = [t for t in used if t not in allowed]
    if disallowed:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used disallowed tools during scoping: {disallowed}', 'evidence_refs': [{'tools_used': used}]}
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No final response to inspect for bulleted memo', 'evidence_refs': [{'tools_used': used}]}
    lines = [l.strip() for l in resp.splitlines() if l.strip()]
    bullet_lines = [l for l in lines if re.match(r'^([\-\*\u2022\+]|\d+[\.\)])\s+', l)]
    has_bullets = len(bullet_lines) >= 2
    if not has_bullets:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Final response does not appear to be a bulleted scoping memo', 'evidence_refs': [{'line_count': len(lines), 'bullet_count': len(bullet_lines)}]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Only allowed scoping tools used and response is a bulleted memo', 'evidence_refs': [{'tools_used': used, 'bullet_count': len(bullet_lines)}]}
