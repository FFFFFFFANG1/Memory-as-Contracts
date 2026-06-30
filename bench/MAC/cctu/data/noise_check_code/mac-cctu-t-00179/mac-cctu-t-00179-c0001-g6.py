def evaluate(trace):
    import re
    resp = str(trace.get('final_response') or '')
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    lines = [ln.rstrip() for ln in resp.splitlines() if ln.strip()]
    table_lines = [ln for ln in lines if ln.lstrip().startswith('|') and ln.rstrip().endswith('|')]
    if len(table_lines) < 2:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no markdown table detected; comparative intent unclear', 'evidence_refs': []}
    # Check two columns: split by | and remove empty boundary cells
    col_counts = []
    for ln in table_lines:
        cells = [c for c in ln.strip().strip('|').split('|')]
        col_counts.append(len(cells))
    if not all(c == 2 for c in col_counts):
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'table is not two-column: column counts {col_counts}', 'evidence_refs': []}
    # Check for plain-text separators outside the table (e.g., '---', '===', 'vs.', '***' as dividers)
    non_table_lines = [ln for ln in lines if ln not in table_lines]
    separator_patterns = [r'^[-=_*]{3,}$', r'^\s*vs\.?\s*$', r'^\s*versus\s*$']
    for ln in non_table_lines:
        s = ln.strip()
        for pat in separator_patterns:
            if re.match(pat, s, re.IGNORECASE):
                return {'observed_followed': False, 'confidence': 'high', 'reason': f'plain-text separator found: {s!r}', 'evidence_refs': []}
    # Find closing row of the table (last table line)
    closing = table_lines[-1]
    cells = [c.strip() for c in closing.strip().strip('|').split('|')]
    trailing_punct = set('.,;:!?')
    for cell in cells:
        if cell and cell[-1] in trailing_punct:
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'closing row has trailing punctuation: {cell!r}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'two-column markdown table, no plain separators, no trailing punctuation on closing row', 'evidence_refs': []}
