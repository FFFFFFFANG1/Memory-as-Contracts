def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    pef = [c for c in calls if c.get('name')=='political_event_finder']
    hlf = [c for c in calls if c.get('name')=='historical_leadership_finder']
    if not pef:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no political_event_finder calls observed','evidence_refs':[]}
    paired = True
    unpaired = []
    for c in pef:
        it = c.get('iteration')
        match = [h for h in hlf if h.get('iteration')==it]
        if not match:
            paired = False
            unpaired.append(it)
    final = trace.get('final_response') or ''
    lines = [l.strip() for l in final.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^\d+[\.\)]\s+', l)]
    is_numbered_list = len(numbered) >= 2 and len(numbered) >= max(1, int(0.5*len(lines)))
    followed = paired and is_numbered_list
    reason = []
    if not paired: reason.append(f'political_event_finder not paired with historical_leadership_finder in iterations {unpaired}')
    if not is_numbered_list: reason.append('final response is not a numbered bullet list')
    if followed: reason.append('tools paired and response is numbered list')
    return {'observed_followed': bool(followed), 'confidence':'high' if pef and final else 'medium','reason':'; '.join(reason),'evidence_refs':[]}
