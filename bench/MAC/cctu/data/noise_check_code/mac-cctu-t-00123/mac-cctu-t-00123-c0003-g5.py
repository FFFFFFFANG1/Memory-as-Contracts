def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    lines = [l for l in text.splitlines() if l.strip()]
    table_lines = [l for l in lines if l.lstrip().startswith('|') and l.rstrip().endswith('|')]
    if len(table_lines) < 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No markdown table detected', 'evidence_refs': []}
    sep_found = any(re.match(r'^\s*\|?\s*:?-{2,}', l) and set(l.replace('|','').replace(':','').replace('-','').strip()) <= set() for l in table_lines)
    if not sep_found:
        sep_found = any(re.search(r'\|\s*:?-{2,}:?\s*\|', l) for l in table_lines)
    if not sep_found:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No markdown table separator row', 'evidence_refs': []}
    data_rows = [l for l in table_lines if not re.search(r'\|\s*:?-{2,}:?\s*\|', l)]
    if len(data_rows) < 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Table has fewer than 2 data rows (need composers + Combined)', 'evidence_refs': []}
    has_combined = any('combined' in l.lower() for l in data_rows[1:])
    if not has_combined:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No final row labeled Combined', 'evidence_refs': []}
    last_data = data_rows[-1]
    if 'combined' not in last_data.lower():
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Combined row is not the final row', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Markdown table with composer rows and final Combined row found', 'evidence_refs': []}
