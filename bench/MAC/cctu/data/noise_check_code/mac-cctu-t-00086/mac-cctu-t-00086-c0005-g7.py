def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    low = text.lower()
    cuisine_terms = ['cuisine', 'dish', 'food', 'culinary', 'gastronom']
    has_cuisine = any(t in low for t in cuisine_terms)
    lines = [l for l in text.splitlines() if l.strip()]
    table_lines = [l for l in lines if l.strip().startswith('|') and l.strip().endswith('|')]
    has_table = len(table_lines) >= 2 and any(re.match(r'^\s*\|[\s:|-]+\|\s*$', l) for l in table_lines)
    comparative_signals = ['compar', 'versus', ' vs', 'differen', 'similar']
    is_comparison = has_cuisine and (has_table or any(s in low for s in comparative_signals))
    if not is_comparison:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'not a tabular regional cuisine comparison context', 'evidence_refs': []}
    if not has_table:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'cuisine comparison present but no markdown table', 'evidence_refs': []}
    # column count from header row
    header = table_lines[0]
    cols = [c for c in header.strip().strip('|').split('|')]
    ncols = len(cols)
    if ncols < 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'table has only {ncols} columns', 'evidence_refs': [header]}
    # check for surrounding narrative prose: non-table non-heading lines
    narrative = []
    for l in lines:
        s = l.strip()
        if s.startswith('|'):
            continue
        if s.startswith('#'):
            continue
        if re.match(r'^[-*]\s', s):
            continue
        # allow a brief title-like single line? Treat any prose as violation
        narrative.append(s)
    if narrative:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'surrounding narrative prose detected', 'evidence_refs': narrative[:3]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'markdown table with {ncols} cols, no surrounding prose', 'evidence_refs': [header]}
