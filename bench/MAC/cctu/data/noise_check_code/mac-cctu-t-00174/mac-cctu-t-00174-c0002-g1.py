def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text = ''
    found_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        if tcs:
            found_tool = True
            break
        c = step.get('content')
        if isinstance(c, str):
            pre_text += '\n' + c
    if not found_tool:
        tcs_flat = trace.get('tool_calls') or []
        if not tcs_flat:
            return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls; cannot confirm pre-tool outline relevance','evidence_refs':[]}
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'no pre-tool brainstorming text found before first tool call','evidence_refs':[]}
    lines = pre_text.splitlines()
    numbered = [l for l in lines if re.match(r'^\s*(\d+)[\.|\)]\s+\S', l)]
    nums = []
    for l in numbered:
        m = re.match(r'^\s*(\d+)', l)
        if m: nums.append(int(m.group(1)))
    distinct = len(set(nums))
    mentions_tool = bool(re.search(r'tool|dependenc', pre_text, re.I))
    if distinct >= 5 and mentions_tool:
        return {'observed_followed': True, 'confidence':'medium','reason':f'found {distinct} numbered items and tool/dependency mention before first tool call','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium','reason':f'pre-tool outline had {distinct} numbered items; tool/dependency mentioned={mentions_tool}','evidence_refs':[]}
