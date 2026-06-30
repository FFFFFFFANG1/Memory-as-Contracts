def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls in trace','evidence_refs':[]}
    # Collect assistant text segments in order with their position relative to tool calls
    # Strategy: for each tool call, find an assistant message after it containing a tally-like one-liner
    tally_pat = re.compile(r'(tally|count|budget|calls?\s*[:=]|\d+\s*/\s*\d+)', re.IGNORECASE)
    missing = []
    # Build a linear sequence of events from trajectory
    events = []
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            for tc in tcs:
                events.append(('tool', tc.get('name','')))
            if content.strip():
                events.append(('text', content))
        else:
            if content.strip():
                events.append(('text', content))
    # For each tool event, check if the next text event contains a one-line tally
    for i, ev in enumerate(events):
        if ev[0] != 'tool':
            continue
        # find next text event
        nxt = None
        for j in range(i+1, len(events)):
            if events[j][0] == 'text':
                nxt = events[j][1]
                break
            # if another tool comes first with no text in between, that's a miss
            if events[j][0] == 'tool':
                nxt = None
                break
        if nxt is None:
            missing.append(ev[1])
            continue
        # one-line tally check: at least one line that matches tally pattern
        lines = [l.strip() for l in nxt.splitlines() if l.strip()]
        has_tally = any(tally_pat.search(l) for l in lines)
        if not has_tally:
            missing.append(ev[1])
    if missing:
        return {'observed_followed': False, 'confidence':'medium','reason': f'No tally report detected after tool call(s): {missing}','evidence_refs':[]}
    return {'observed_followed': True, 'confidence':'medium','reason':'Tally-like one-liner detected after each tool call','evidence_refs':[]}
