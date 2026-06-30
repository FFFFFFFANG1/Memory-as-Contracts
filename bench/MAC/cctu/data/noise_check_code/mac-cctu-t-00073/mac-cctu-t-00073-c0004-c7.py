def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    traj = trace.get('trajectory') or []
    for step in traj:
        c = step.get('content') if isinstance(step, dict) else None
        if c:
            text += '\n' + str(c)
    tool_calls = trace.get('tool_calls') or []
    chosen = []
    seen = set()
    for tc in tool_calls:
        n = tc.get('name')
        if n and n not in seen:
            seen.add(n)
            chosen.append(n)
    if not chosen:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found to review.', 'evidence_refs': []}
    low = text.lower()
    comparative_markers = ['prefer', 'preferred', 'rather than', 'instead of', 'over ', 'compared to', 'versus', ' vs ', 'alternative', 'better than', 'chosen over', 'rather']
    justified = []
    missing = []
    for name in chosen:
        nl = name.lower()
        idx = low.find(nl)
        if idx < 0:
            missing.append(name)
            continue
        window = low[max(0, idx-400): idx+400]
        if any(m in window for m in comparative_markers):
            justified.append(name)
        else:
            missing.append(name)
    if not missing:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Found comparative justification near each chosen tool: {justified}.', 'evidence_refs': justified}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'No written justification comparing to alternatives for: {missing}.', 'evidence_refs': missing}
