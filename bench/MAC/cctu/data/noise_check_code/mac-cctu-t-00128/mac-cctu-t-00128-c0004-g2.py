def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no response','evidence_refs':[]}
    tool_calls = trace.get('tool_calls') or []
    names = [tc.get('name','') for tc in tool_calls]
    primary = None
    for n in names:
        if n == 'ocean_depth_analyzer':
            primary = n; break
    if primary is None and names:
        primary = names[0]
    # Split into sentences
    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', resp) if s.strip()]
    two_sentences = len(sentences) == 2
    cites = False
    if primary:
        cites = primary.lower() in resp.lower() or primary.replace('_',' ').lower() in resp.lower()
    followed = two_sentences and cites
    return {'observed_followed': bool(followed), 'confidence':'medium','reason': f'sentences={len(sentences)}, primary={primary}, cites={cites}','evidence_refs':[]}
