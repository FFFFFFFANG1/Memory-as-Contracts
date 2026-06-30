def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_names = ['comet_event_tracker','historical_event_finder','incident_search_tool','international_agreement_finder','legislative_action_retriever','organization_membership_tracker']
    pre_text = ''
    first_tool_idx = None
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            first_tool_idx = i
            break
        pre_text += '\n' + (step.get('content') or '')
    if first_tool_idx is None:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls found','evidence_refs':[]}
    lines = [l.rstrip() for l in pre_text.splitlines() if l.strip()]
    numbered = [l for l in lines if re.match(r'^\s*(\d+[\.\)]|\(\d+\))\s+', l)]
    if len(numbered) < 2:
        return {'observed_followed': False, 'confidence':'high','reason':'No numbered plan found before first tool invocation','evidence_refs':[]}
    with_tool = 0
    for l in numbered:
        low = l.lower()
        if any(t in low for t in tool_names):
            with_tool += 1
    if with_tool >= max(1, len(numbered)//2) and with_tool >= 1:
        if with_tool >= len(numbered) - 1:
            return {'observed_followed': True, 'confidence':'high','reason': f'Found {len(numbered)} numbered steps with tool names ({with_tool})','evidence_refs':[]}
        return {'observed_followed': True, 'confidence':'medium','reason': f'{with_tool}/{len(numbered)} numbered steps mention tools','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium','reason': f'Numbered plan present but tools not listed per step ({with_tool}/{len(numbered)})','evidence_refs':[]}
