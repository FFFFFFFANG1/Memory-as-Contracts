def evaluate(trace):
    import re
    allowed = {'urban_area_identifier','business_district_locator'}
    calls = trace.get('tool_calls') or []
    used = [c.get('name') for c in calls if c.get('name')]
    bad = [n for n in used if n not in allowed]
    final = (trace.get('final_response') or '').strip()
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Used disallowed tools: {sorted(set(bad))}', 'evidence_refs': bad}
    # one paragraph check: no blank line separating paragraphs
    paragraphs = [p for p in re.split(r'\n\s*\n', final) if p.strip()]
    if len(paragraphs) > 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Response has {len(paragraphs)} paragraphs, not one', 'evidence_refs': []}
    # check no committed numeric final answer - look for patterns like 'the answer is X', 'final: N', or a standalone numeric conclusion
    low = final.lower()
    commit_patterns = [r'\bthe answer is\b', r'\bfinal answer\b', r'\bi conclude\b.*\d', r'\bdefinitively\b.*\d', r'\bis exactly\s+\d']
    for pat in commit_patterns:
        if re.search(pat, low):
            return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Appears to commit to a final answer: pattern {pat}', 'evidence_refs': [pat]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Only allowed tools used; single paragraph; no explicit numeric commitment detected', 'evidence_refs': used}
