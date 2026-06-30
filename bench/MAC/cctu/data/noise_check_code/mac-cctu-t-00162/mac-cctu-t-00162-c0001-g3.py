def evaluate(trace):
    import re
    allowed = {'historical_hemisphere_locator_v2','historical_location_finder'}
    tcs = trace.get('tool_calls') or []
    traj = trace.get('trajectory') or []
    if not tcs:
        return {'observed_followed': None,'confidence':'unknown','reason':'no tool calls to assess scoping phase','evidence_refs':[]}
    # Identify scoping phase: leading contiguous calls before any tool outside allowed appears,
    # or before a clearly later phase. We treat the leading prefix as the scoping phase.
    scoping_calls = []
    for tc in tcs:
        name = tc.get('name')
        if name in allowed:
            scoping_calls.append(tc)
        else:
            break
    if not scoping_calls:
        return {'observed_followed': False,'confidence':'medium','reason': f'first tool call {tcs[0].get("name")} is not an allowed scoping tool','evidence_refs':[str(tcs[0].get('name'))]}
    # Check assistant content during scoping phase for numerical conclusions.
    last_iter = scoping_calls[-1].get('iteration')
    num_pattern = re.compile(r'\b\d+(?:\.\d+)?\b')
    conclusion_markers = ['therefore','thus','the answer','conclude','conclusion','final answer','in total','equals','=']
    offending = []
    for step in traj:
        it = step.get('iteration')
        if it is None or last_iter is None or it > last_iter:
            continue
        content = (step.get('content') or '').lower()
        if not content:
            continue
        if num_pattern.search(content) and any(m in content for m in conclusion_markers):
            offending.append(content[:120])
    if offending:
        return {'observed_followed': False,'confidence':'medium','reason':'numerical conclusion stated during scoping phase','evidence_refs': offending[:2]}
    return {'observed_followed': True,'confidence':'medium','reason':'scoping phase used only allowed tools and avoided numerical conclusions','evidence_refs':[tc.get('name') for tc in scoping_calls]}
