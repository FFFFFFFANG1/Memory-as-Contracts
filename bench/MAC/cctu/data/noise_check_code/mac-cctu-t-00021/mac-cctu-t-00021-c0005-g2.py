def evaluate(trace):
    import re
    text = trace.get('final_response','') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence':'unknown','reason':'empty response','evidence_refs':[]}
    lines = text.splitlines()
    numbered = [l for l in lines if re.match(r'^\s*\d+[\.\)]\s+\S', l)]
    has_numbered = len(numbered) >= 2
    # detect markdown table: at least one line with multiple pipes and a separator row
    pipe_lines = [l for l in lines if l.count('|') >= 2]
    sep_row = any(re.match(r'^\s*\|?\s*:?-{2,}', l) and l.count('|') >= 2 for l in lines)
    is_table = sep_row or len(pipe_lines) >= 3
    # check for leading identifier before agreement name in numbered items
    # e.g., '1. A1: Treaty of ...' or '1. ID-123 - Treaty ...'
    leading_id = False
    for l in numbered:
        body = re.sub(r'^\s*\d+[\.\)]\s+', '', l).strip()
        # strip bold markers
        body_clean = re.sub(r'^\*+', '', body).strip()
        m = re.match(r'^([A-Z]{1,4}[-_]?\d+|\d+[-_]?[A-Z]*|#\d+|ID[:\-\s]*\d+)\s*[:\-\u2013]\s+', body_clean)
        if m:
            leading_id = True
            break
    followed = has_numbered and (not is_table) and (not leading_id)
    reason_parts = []
    reason_parts.append(f'numbered_items={len(numbered)}')
    reason_parts.append(f'is_table={is_table}')
    reason_parts.append(f'leading_id={leading_id}')
    conf = 'high' if has_numbered else 'medium'
    return {'observed_followed': bool(followed), 'confidence': conf, 'reason': '; '.join(reason_parts), 'evidence_refs': []}
