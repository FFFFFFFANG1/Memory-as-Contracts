def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    # collect names of tools actually invoked in order
    invoked = [tc.get('name','') for tc in tool_calls if tc.get('name')]
    # find content of assistant steps that occur before first tool call
    pre_text = ''
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            pre_text += '\n' + content
            break
        pre_text += '\n' + content
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'no planning text before first tool call','evidence_refs':[]}
    low = pre_text.lower()
    # heuristic: must look like a roadmap/plan listing steps
    has_plan_marker = any(k in low for k in ['plan','roadmap','steps','sub-task','subtask','will call','i will','outline'])
    # check each invoked tool is mentioned in pre_text
    missing = []
    for name in set(invoked):
        if name.lower() not in low:
            # also accept partial token match
            tokens = name.lower().split('_')
            if not all(t in low for t in tokens if len(t)>3):
                missing.append(name)
    if not has_plan_marker:
        return {'observed_followed': False,'confidence':'medium','reason':'no explicit roadmap/plan language before tool use','evidence_refs':[pre_text[:200]]}
    if missing:
        return {'observed_followed': False,'confidence':'medium','reason':f'plan missing tools: {missing}','evidence_refs':[pre_text[:200]]}
    return {'observed_followed': True,'confidence':'medium','reason':'pre-tool roadmap enumerates invoked tools','evidence_refs':[pre_text[:200]]}
