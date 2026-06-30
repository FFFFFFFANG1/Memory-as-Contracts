def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Check single paragraph: no blank line separators
    if re.search(r'\n\s*\n', resp):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'multiple paragraphs detected', 'evidence_refs': []}
    # Check no tables (markdown pipe tables)
    lines = resp.split('\n')
    pipe_lines = [l for l in lines if l.count('|') >= 2]
    if len(pipe_lines) >= 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'table-like structure detected', 'evidence_refs': []}
    if re.search(r'\|[-: ]+\|', resp):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'markdown table separator', 'evidence_refs': []}
    # Check numeric prefixes (e.g., '1. ', '2) ') at line starts
    for l in lines:
        if re.match(r'^\s*\d+[\.\)]\s+', l):
            return {'observed_followed': False, 'confidence': 'high', 'reason': 'numeric prefix found', 'evidence_refs': [l[:60]]}
    # Check identifier headers like '# Title', '## ...', or 'ID:' style
    for l in lines:
        if re.match(r'^\s*#{1,6}\s+\S', l):
            return {'observed_followed': False, 'confidence': 'high', 'reason': 'markdown header found', 'evidence_refs': [l[:60]]}
        if re.match(r'^\s*[A-Z][A-Za-z _-]{0,40}:\s', l) and len(l) < 80:
            # heuristic identifier header like 'Name: ...'
            # allow if it's just a sentence; require it to look like a label (short, no period before colon)
            label = l.split(':',1)[0].strip()
            if ' ' not in label or label.isupper():
                return {'observed_followed': False, 'confidence': 'medium', 'reason': 'identifier header detected', 'evidence_refs': [l[:60]]}
    # Bullet markers also imply structure, not prose
    for l in lines:
        if re.match(r'^\s*[-*•]\s+', l):
            return {'observed_followed': False, 'confidence': 'high', 'reason': 'bullet list detected', 'evidence_refs': [l[:60]]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'single prose paragraph without tables, numeric prefixes, or headers', 'evidence_refs': []}
