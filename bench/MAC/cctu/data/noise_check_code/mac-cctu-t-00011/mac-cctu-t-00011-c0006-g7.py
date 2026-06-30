def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = resp.splitlines()
    table_lines = [l for l in lines if l.count('|') >= 2]
    has_sep = any(re.search(r'\|\s*:?-{2,}', l) for l in lines)
    has_table = len(table_lines) >= 2 and has_sep
    pct_matches = re.findall(r'(\d+\.\d+)\s*%', resp)
    two_dec = [p for p in pct_matches if len(p.split('.')[1]) == 2]
    bad = [p for p in pct_matches if len(p.split('.')[1]) != 2]
    if not has_table:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no side-by-side comparison table detected', 'evidence_refs': []}
    if not pct_matches:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'no vote-share percentages found', 'evidence_refs': []}
    if bad:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'percentages not rounded to two decimals: {bad[:5]}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'table present with {len(two_dec)} two-decimal percentages', 'evidence_refs': []}
