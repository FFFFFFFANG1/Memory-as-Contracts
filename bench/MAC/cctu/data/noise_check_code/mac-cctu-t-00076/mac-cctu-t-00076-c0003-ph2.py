def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    if not calls and not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No trajectory evidence', 'evidence_refs': []}
    bad = [c.get('name') for c in calls if c.get('name') and c.get('name') != 'award_winner_retriever']
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Non-permitted tools used: {sorted(set(bad))}', 'evidence_refs': bad}
    lines = [l.strip() for l in final.splitlines() if l.strip()]
    bullet_lines = [l for l in lines if re.match(r'^([\-\*\u2022\u00b7]|\d+[\.)])\s+', l)]
    if not lines:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Empty final response', 'evidence_refs': []}
    if len(bullet_lines) < 2:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Final response is not a bulleted summary', 'evidence_refs': lines[:3]}
    year_hits = sum(1 for l in bullet_lines if re.search(r'\b(19|20)\d{2}\b', l))
    if year_hits < 1:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'Bullets do not appear to reference candidate years', 'evidence_refs': bullet_lines[:3]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Only award_winner_retriever used; bulleted year summary returned', 'evidence_refs': bullet_lines[:3]}
