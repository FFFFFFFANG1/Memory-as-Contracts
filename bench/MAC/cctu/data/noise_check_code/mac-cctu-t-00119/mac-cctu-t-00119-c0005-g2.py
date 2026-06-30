def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    md_patterns = [r'^\s*#', r'^\s*\*\s', r'^\s*-\s', r'^\s*\d+\.\s', r'\|.*\|', r'^\s*>\s', r'```', r'\*\*', r'__', r'^\s*\|']
    md_hits = []
    for p in md_patterns:
        if re.search(p, text, re.MULTILINE):
            md_hits.append(p)
    has_table = '|' in text and re.search(r'\|.*\|', text) is not None
    last = text.rstrip()
    ends_q = last.endswith('?')
    followed = (not md_hits) and (not has_table) and ends_q
    reason_parts = []
    if md_hits: reason_parts.append('markdown patterns: '+str(md_hits))
    if has_table: reason_parts.append('table-like pipes present')
    if not ends_q: reason_parts.append('does not end with question mark')
    if not reason_parts: reason_parts.append('plain prose ending with question')
    return {'observed_followed': bool(followed), 'confidence':'high' if followed or md_hits or not ends_q else 'medium','reason':'; '.join(reason_parts),'evidence_refs':[]}
