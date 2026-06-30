def evaluate(trace):
    import re
    allowed = {'event_locator'}
    calls = trace.get('tool_calls') or []
    used = [c.get('name') for c in calls]
    bad_tools = [n for n in used if n and n not in allowed]
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    lines = [ln.strip() for ln in final.splitlines() if ln.strip()]
    bullet_lines = [ln for ln in lines if re.match(r'^([\-\*\+\u2022]|\d+[\.)])\s+', ln)]
    has_bullets = len(bullet_lines) >= 2
    commit_patterns = [
        r'\bthe\s+(?:final\s+)?(?:answer|date)\s+is\b',
        r'\bI\s+(?:can\s+)?confirm\b',
        r'\bdefinitively\b',
        r'\bthe\s+case\s+(?:is|was)\s+(?:decided|filed)\s+on\b',
    ]
    text_low = final.lower()
    committed = any(re.search(p, text_low) for p in commit_patterns)
    reasons = []
    ok = True
    if bad_tools:
        ok = False
        reasons.append(f'used disallowed tools: {sorted(set(bad_tools))}')
    if not has_bullets:
        ok = False
        reasons.append('no bullet-point list of candidates')
    if committed:
        ok = False
        reasons.append('appears to commit to a final date')
    if ok:
        reasons.append('only event_locator used, bullets present, no final date commitment')
    return {'observed_followed': ok, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
