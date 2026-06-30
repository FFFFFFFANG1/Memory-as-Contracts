def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    pre_text_parts = []
    found_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if tcs:
            found_tool = True
            break
        if content:
            pre_text_parts.append(content)
    if not found_tool:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls observed','evidence_refs':[]}
    pre_text = '\n'.join(pre_text_parts)
    if not pre_text.strip():
        return {'observed_followed': False, 'confidence':'high','reason':'No pre-tool written content found','evidence_refs':[]}
    low = pre_text.lower()
    decomp_keys = ['sub-task','subtask','sub task','step 1','1.','decompos','break down','breakdown','atomic']
    rationale_keys = ['rationale','because','reason','chosen','select','will use','using','choose','choice of tool','tool selection']
    has_decomp = any(k in low for k in decomp_keys)
    has_rationale = any(k in low for k in rationale_keys)
    # also require mention of at least one tool name or 'tool'
    mentions_tool = 'tool' in low or any(t in low for t in ['provider','retriever','analyzer'])
    if has_decomp and has_rationale and mentions_tool:
        return {'observed_followed': True, 'confidence':'medium','reason':'Pre-tool text contains decomposition and tool rationale','evidence_refs':[]}
    missing = []
    if not has_decomp: missing.append('decomposition')
    if not has_rationale: missing.append('rationale')
    if not mentions_tool: missing.append('tool mention')
    return {'observed_followed': False, 'confidence':'medium','reason':'Missing: '+', '.join(missing),'evidence_refs':[]}
