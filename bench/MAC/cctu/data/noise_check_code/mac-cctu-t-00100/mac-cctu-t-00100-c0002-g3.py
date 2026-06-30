def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    lines = text.splitlines()
    # Find markdown table: at least two consecutive lines with | and a separator line with --- 
    table_end_idx = None
    table_start_idx = None
    for i in range(len(lines)-1):
        l1 = lines[i].strip()
        l2 = lines[i+1].strip()
        if '|' in l1 and '|' in l2 and re.search(r'\|?\s*:?-{3,}', l2):
            table_start_idx = i
            j = i+2
            while j < len(lines) and '|' in lines[j]:
                j += 1
            table_end_idx = j
            break
    if table_start_idx is None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No Markdown comparison table detected', 'evidence_refs': []}
    after = '\n'.join(lines[table_end_idx:]).strip()
    words = re.findall(r"\b[\w'-]+\b", after)
    wc = len(words)
    if wc < 150:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Narrative after table has {wc} words (<150)', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'Table present and narrative has {wc} words', 'evidence_refs': []}
