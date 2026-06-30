def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    final = (trace.get('final_response') or '')
    traj = trace.get('trajectory') or []
    # Gather any assistant text prior to (or in absence of) tool calls
    texts = []
    for step in traj:
        c = step.get('content') if isinstance(step, dict) else None
        if c:
            texts.append(c)
    combined = '\n'.join(texts) if texts else final
    if not combined:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No assistant text found', 'evidence_refs': []}
    if len(tool_calls) > 0:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Agent invoked {len(tool_calls)} tool(s) despite no-tool constraint', 'evidence_refs': [{'tool_calls': len(tool_calls)}]}
    low = combined.lower()
    restate_markers = ['restate', 'the user', 'the question', 'you asked', 'your question', 'rephrase', 'understand']
    decomp_markers = ['sub-task', 'subtask', 'sub task', 'decompos', 'step 1', 'steps:', 'plan:', '1.', '1)', 'first,', 'breakdown', 'break down']
    has_restate = any(m in low for m in restate_markers)
    has_decomp = any(m in low for m in decomp_markers)
    if has_restate and has_decomp:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Found restatement cues and sub-task decomposition markers, no tools invoked', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'low', 'reason': f'Missing restatement={not has_restate} or decomposition={not has_decomp}', 'evidence_refs': []}
