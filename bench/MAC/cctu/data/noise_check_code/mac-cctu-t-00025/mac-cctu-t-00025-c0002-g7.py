def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_steps = []
    for i, step in enumerate(traj):
        tcs = step.get('tool_calls') or []
        if tcs:
            content = step.get('content') or ''
            tool_steps.append((i, content, tcs))
    if not tool_steps:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool invocations found', 'evidence_refs': []}
    spoken_markers = ['audience','folks','everyone','listeners','viewers','ladies and gentlemen','live','now','next','let me','i will','let\'s','tune in','stay with','watch','listening','watching']
    missing = []
    for idx, content, tcs in tool_steps:
        text = (content or '').strip()
        if not text:
            missing.append(idx)
            continue
        low = text.lower()
        if not any(m in low for m in spoken_markers):
            missing.append(idx)
    final = (trace.get('final_response') or '').strip()
    read_aloud_markers = ['final answer','the answer is','answer:','here is the answer','reading aloud','aloud']
    final_low = final.lower()
    read_aloud_ok = any(m in final_low for m in read_aloud_markers) or len(final) > 0
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Tool steps without spoken-style preamble at indices {missing}', 'evidence_refs': [{'step_index': i} for i in missing]}
    if not read_aloud_ok:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'Final response lacks read-aloud framing', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Each tool call preceded by spoken-style content and final response present', 'evidence_refs': []}
