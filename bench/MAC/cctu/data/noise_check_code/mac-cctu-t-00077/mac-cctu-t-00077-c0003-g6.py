def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls made; constraint not exercised.', 'evidence_refs': []}
    # Find index/iteration of first tool call
    first_iter = None
    for tc in tool_calls:
        it = tc.get('iteration')
        if it is not None:
            first_iter = it if first_iter is None else min(first_iter, it)
    pre_text = ''
    for i, step in enumerate(traj):
        content = step.get('content') or ''
        has_calls = bool(step.get('tool_calls'))
        if has_calls:
            pre_text += '\n' + content
            break
        pre_text += '\n' + content
    mermaid_pat = re.search(r'(mermaid|graph\s+(TD|LR|TB|RL)|flowchart\s+(TD|LR|TB|RL))', pre_text, re.IGNORECASE)
    acyclic_pat = re.search(r'acyclic|no\s+cycle|dag|self[- ]check', pre_text, re.IGNORECASE)
    if mermaid_pat and acyclic_pat:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Mermaid diagram and acyclic self-check present before first tool call.', 'evidence_refs': [mermaid_pat.group(0), acyclic_pat.group(0)]}
    if not mermaid_pat and not acyclic_pat:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'No Mermaid diagram or acyclic self-check before first tool call.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Missing either Mermaid diagram or acyclic self-check before first tool call.', 'evidence_refs': [str(bool(mermaid_pat)), str(bool(acyclic_pat))]}
