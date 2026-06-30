def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [ln for ln in resp.splitlines() if ln.strip() != '']
    if not lines:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no content lines', 'evidence_refs': []}
    table_lines = [ln for ln in lines if ln.lstrip().startswith('|')]
    if len(table_lines) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no markdown table detected', 'evidence_refs': [resp[:200]]}
    sep_found = any(re.match(r'^\s*\|?\s*:?-{2,}', ln) and set(ln.replace('|','').replace(':','').replace('-','').strip()) == set() for ln in lines)
    if not sep_found:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'markdown table separator row missing', 'evidence_refs': [resp[:200]]}
    non_table = [ln for ln in lines if not ln.lstrip().startswith('|')]
    if non_table:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'prose outside table: {non_table[:2]}', 'evidence_refs': non_table[:3]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'single markdown table with no prose outside', 'evidence_refs': []}
