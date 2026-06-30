def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls present', 'evidence_refs': []}
    # Build sequence of assistant messages following each tool call
    # Heuristic: a reflection step is an assistant text message after tool outputs
    cite_pat = re.compile(r'(source\s*[:\-]|cite|citation|provenance|ref(erence)?\s*[:\-]|https?://|\[\d+\]|according to|retrieved from|via\s+\w+_)', re.I)
    # Look at assistant content segments and check if each tool call has an accompanying citation in subsequent reflection
    missing = []
    found = 0
    for tc in tool_calls:
        idx = tc.get('index')
        it = tc.get('iteration')
        tname = tc.get('name','')
        # Find assistant reflection after this tool call
        reflection_text = ''
        for step in traj:
            if step.get('role') in (None,'assistant'):
                # consider steps after this iteration
                step_iter = step.get('iteration')
                if step_iter is None or it is None or step_iter >= it:
                    c = step.get('content') or ''
                    if c:
                        reflection_text += '\n' + c
        if cite_pat.search(reflection_text) or tname in reflection_text:
            found += 1
        else:
            missing.append(tname)
    if not missing:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'All {found} tool outputs appear to have provenance citations in reflections', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Missing provenance citations for tools: {missing}', 'evidence_refs': missing}
