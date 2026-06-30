import re
def evaluate(trace):
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls executed; cannot verify pre-tool scratch output.', 'evidence_refs': []}
    first_tc_iter = None
    for tc in tool_calls:
        it = tc.get('iteration')
        if it is None:
            it = tc.get('index')
        if it is None:
            continue
        if first_tc_iter is None or it < first_tc_iter:
            first_tc_iter = it
    pre_contents = []
    for i, step in enumerate(traj):
        step_iter = step.get('iteration', i)
        has_tc = bool(step.get('tool_calls'))
        content = step.get('content') or ''
        if first_tc_iter is not None and step_iter < first_tc_iter:
            pre_contents.append(content)
        elif first_tc_iter is not None and step_iter == first_tc_iter and not has_tc:
            pre_contents.append(content)
        elif first_tc_iter is None and not has_tc:
            pre_contents.append(content)
        if has_tc:
            break
    combined = '\n'.join(pre_contents)
    fences = re.findall(r'```[\s\S]*?```', combined)
    arrow_re = re.compile(r'(->|-->|→|=>)')
    found = False
    for f in fences:
        if len(arrow_re.findall(f)) >= 1:
            found = True
            break
    if found:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Fenced code block containing arrow chain found before first tool call.', 'evidence_refs': []}
    if not fences:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No fenced code block produced before first tool call.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Fenced code block present but no ASCII arrow chain detected before first tool call.', 'evidence_refs': []}
