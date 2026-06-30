def evaluate(trace):
    traj = trace.get('trajectory') or []
    steps_with_calls = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            steps_with_calls.append((i, len(tcs), step.get('content') or ''))
    if not steps_with_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls in trajectory', 'evidence_refs': []}
    # Check one call per step
    multi = [(i,n) for (i,n,_) in steps_with_calls if n > 1]
    if multi:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'step(s) with multiple tool calls: {multi}', 'evidence_refs': [i for i,_ in multi]}
    # Check intermediate summarization between calls
    # Between consecutive tool-calling steps, there should be assistant text content summarizing
    missing_summary = []
    for k in range(1, len(steps_with_calls)):
        prev_idx = steps_with_calls[k-1][0]
        cur_idx = steps_with_calls[k][0]
        # look at assistant content of current step or any step between
        summary_text = ''
        for j in range(prev_idx+1, cur_idx+1):
            c = traj[j].get('content') or ''
            if isinstance(c, str):
                summary_text += ' ' + c
        if len(summary_text.strip()) < 10:
            missing_summary.append((prev_idx, cur_idx))
    if missing_summary:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'missing natural-language summary between calls: {missing_summary}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'one tool call per step with intermediate summaries', 'evidence_refs': [i for i,_,_ in steps_with_calls]}
