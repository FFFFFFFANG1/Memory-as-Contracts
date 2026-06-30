def evaluate(trace):
    import re
    tcs = trace.get('tool_calls') or []
    retriever_like = [c for c in tcs if re.search(r'retriev|finder|search|identifier|analyzer', (c.get('name') or '').lower())]
    distinct = {c.get('name') for c in retriever_like if c.get('name')}
    if len(distinct) < 2:
        return {'observed_followed': False, 'confidence':'high', 'reason': f'Only {len(distinct)} distinct retriever-like tool(s) used: {sorted(distinct)}', 'evidence_refs': []}
    # Look for intermediate reasoning trace mentioning linking entity between hops, before final answer
    traj = trace.get('trajectory') or []
    intermediate_text = ''
    for step in traj:
        content = step.get('content') or ''
        if content:
            intermediate_text += '\n' + content
    final = trace.get('final_response') or ''
    # Remove final response tail from intermediate
    if final and intermediate_text.endswith(final):
        intermediate_text = intermediate_text[:-len(final)]
    text = intermediate_text.lower()
    link_kw = any(k in text for k in ['linking entity','link entity','bridge entity','common entity','shared entity','linking:','link:','bridge:','connects','linking term'])
    if not link_kw:
        return {'observed_followed': None, 'confidence':'low', 'reason':'No explicit linking-entity reasoning trace detected between hops.', 'evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium', 'reason': f'Chained {len(distinct)} retriever-like tools and intermediate trace references linking entity.', 'evidence_refs': sorted(distinct)}
