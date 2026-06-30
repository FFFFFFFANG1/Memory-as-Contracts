def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    header_idx = None
    for i, l in enumerate(lines):
        if '|' in l and re.search(r'date', l, re.I) and re.search(r'outcome', l, re.I):
            header_idx = i
            break
    if header_idx is None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No markdown table with Date and Outcome headers found', 'evidence_refs': []}
    if header_idx + 1 >= len(lines):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Missing separator row', 'evidence_refs': []}
    sep = lines[header_idx + 1]
    if not re.match(r'^\|?\s*:?-{2,}:?\s*\|\s*:?-{2,}:?\s*\|?$', sep):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Separator row not a valid 2-col markdown separator', 'evidence_refs': [sep]}
    header_cells = [c.strip() for c in lines[header_idx].strip('|').split('|')]
    if len(header_cells) != 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Header has {len(header_cells)} columns, expected 2', 'evidence_refs': [lines[header_idx]]}
    if not (re.fullmatch(r'date', header_cells[0], re.I) and re.fullmatch(r'outcome', header_cells[1], re.I)):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Headers not exactly Date and Outcome', 'evidence_refs': header_cells}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Found two-column markdown table with Date and Outcome headers', 'evidence_refs': [lines[header_idx], sep]}
