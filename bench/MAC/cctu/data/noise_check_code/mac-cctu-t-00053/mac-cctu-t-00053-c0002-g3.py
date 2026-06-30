def evaluate(trace):
    import re, json
    calls = trace.get('tool_calls') or []
    beach_count = sum(1 for c in calls if (c.get('name') or '') == 'beach_locator')
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    is_json = False
    try:
        parsed = json.loads(final)
        if isinstance(parsed, (dict, list)):
            is_json = True
    except Exception:
        is_json = False
    lines = [l.strip() for l in final.splitlines() if l.strip()]
    bullet_lines = [l for l in lines if re.match(r'^([\*\-\+]|\d+\.)\s+', l)]
    has_bullets = len(bullet_lines) >= 2
    ok_count = beach_count >= 3
    ok_format = has_bullets and not is_json
    followed = ok_count and ok_format
    return {
        'observed_followed': bool(followed),
        'confidence': 'high',
        'reason': f'beach_locator calls={beach_count} (need>=3); bullets={len(bullet_lines)}; json_wrapped={is_json}',
        'evidence_refs': []
    }
