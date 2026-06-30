def evaluate(trace):
    resp = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not resp.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty response', 'evidence_refs': []}
    if not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls to summarize in preamble', 'evidence_refs': []}
    lines = [ln for ln in resp.split('\n') if ln.strip()]
    if len(lines) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'response lacks multi-line structure (preamble + landmark name)', 'evidence_refs': []}
    # Last non-empty line should be landmark name (short)
    last = lines[-1].strip()
    preamble = '\n'.join(lines[:-1])
    # Landmark name should be relatively short (a name, not a sentence)
    if len(last.split()) > 15:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'final line does not look like a standalone landmark name', 'evidence_refs': []}
    # Preamble should be verbose
    if len(preamble.split()) < 20:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'preamble is not verbose enough', 'evidence_refs': []}
    # Preamble should reference each tool call (by tool name or summary token)
    preamble_low = preamble.lower()
    tool_names = []
    for tc in tool_calls:
        name = tc.get('name') or ''
        if name:
            tool_names.append(name)
    missing = []
    for name in tool_names:
        tokens = [t for t in name.lower().replace('-', '_').split('_') if len(t) > 3]
        if tokens and not any(t in preamble_low for t in tokens):
            missing.append(name)
    if missing and len(missing) == len(tool_names):
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'preamble does not summarize tool calls: ' + ', '.join(missing[:3]), 'evidence_refs': []}
    if missing:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'preamble may omit some tool calls: ' + ', '.join(missing[:3]), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'verbose preamble summarizes tool calls; landmark name on final line', 'evidence_refs': []}
