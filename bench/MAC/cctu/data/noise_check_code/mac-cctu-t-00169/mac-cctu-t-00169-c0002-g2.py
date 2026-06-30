def evaluate(trace):
    import re
    tools_used = []
    for tc in trace.get('tool_calls', []) or []:
        n = tc.get('name')
        if n and n not in tools_used:
            tools_used.append(n)
    if not tools_used:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found to evaluate justifications.', 'evidence_refs': []}
    texts = []
    for step in trace.get('trajectory', []) or []:
        c = step.get('content')
        if isinstance(c, str) and c.strip():
            texts.append(c)
    fr = trace.get('final_response') or ''
    if isinstance(fr, str) and fr.strip():
        texts.append(fr)
    combined = '\n'.join(texts)
    if not combined.strip():
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No assistant content available to contain justifications.', 'evidence_refs': []}
    missing = []
    justified = []
    # split text into sentences for justification detection
    sentences = re.split(r'(?<=[.!?])\s+', combined)
    justify_kw = re.compile(r'(because|since|in order to|to (?:retrieve|find|identify|calculate|compute|analyze|locate|determine|get|obtain)|most precise|best suited|chosen|selected|use[ds]? (?:to|for)|appropriate|ideal|specifically|justif)', re.I)
    for tool in tools_used:
        tool_pat = re.compile(re.escape(tool).replace('_', r'[ _]?'), re.I)
        found = False
        for s in sentences:
            if tool_pat.search(s) and justify_kw.search(s):
                found = True
                break
        if found:
            justified.append(tool)
        else:
            missing.append(tool)
    if not missing:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'Found justification sentences for all {len(tools_used)} tool(s): {justified}.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Missing one-sentence justifications for tools: {missing}.', 'evidence_refs': []}
