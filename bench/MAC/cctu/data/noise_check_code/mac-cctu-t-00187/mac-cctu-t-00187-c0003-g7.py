def evaluate(trace):
    import re
    resp = trace.get('final_response') or ''
    calls = trace.get('tool_calls') or []
    if not resp.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Find a bibliography-like header
    header_match = re.search(r'(?im)^[\s#*_>-]*(bibliography|references|citations|works cited|sources)\b.*$', resp)
    if not header_match:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no bibliography section header found', 'evidence_refs': []}
    bib_text = resp[header_match.end():]
    # Count numbered entries like '1.' '2)' '[1]' at line starts
    entries = re.findall(r'(?m)^\s*(?:\[\d+\]|\(\d+\)|\d+[.)])\s+\S', bib_text)
    n_calls = len(calls)
    if n_calls == 0:
        followed = len(entries) == 0 or bool(re.search(r'(?i)no tool', bib_text))
        return {'observed_followed': followed, 'confidence': 'low', 'reason': f'no tool calls; entries={len(entries)}', 'evidence_refs': []}
    if len(entries) < n_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'found {len(entries)} numbered entries but {n_calls} tool calls', 'evidence_refs': []}
    # Ensure bibliography is after answer body (header not at very start)
    after_body = header_match.start() > 0 and bool(resp[:header_match.start()].strip())
    if not after_body:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'bibliography not preceded by an answer body', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': f'bibliography with {len(entries)} numbered entries for {n_calls} tool calls', 'evidence_refs': []}
