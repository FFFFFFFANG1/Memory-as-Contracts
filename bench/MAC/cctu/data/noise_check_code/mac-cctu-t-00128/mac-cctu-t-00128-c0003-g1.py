def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    calls = trace.get('tool_calls') or []
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    # Determine primary tool: most used, prefer ocean_depth_analyzer if present
    names = [c.get('name','') for c in calls]
    if not names:
        return {'observed_followed': None,'confidence':'unknown','reason':'no tool calls to identify primary tool','evidence_refs':[]}
    counts = {}
    for n in names:
        counts[n] = counts.get(n,0)+1
    primary = max(counts, key=lambda k: counts[k])
    # Count sentences (split on . ! ?)
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', resp) if s.strip()]
    n_sent = len(sentences)
    two_sent = (n_sent == 2)
    cites = primary.lower() in resp.lower() or primary.replace('_',' ').lower() in resp.lower()
    followed = two_sent and cites
    return {'observed_followed': bool(followed),'confidence':'medium','reason': f'sentences={n_sent}, primary_tool={primary}, cited={cites}','evidence_refs':[]}
