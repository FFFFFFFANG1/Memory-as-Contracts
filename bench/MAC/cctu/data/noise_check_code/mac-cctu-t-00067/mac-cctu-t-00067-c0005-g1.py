def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty response', 'evidence_refs': []}
    if not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls to audit', 'evidence_refs': []}
    # Check conclusion phrase
    phrase_re = re.compile(r'Cultural artifact identified:\s*.+\.', re.IGNORECASE)
    matches = list(phrase_re.finditer(response))
    if not matches:
        return {'observed_followed': False, 'confidence': 'high', 'reason': "missing 'Cultural artifact identified: [result].' phrase", 'evidence_refs': []}
    # Check audit list contains each tool name in chronological order
    ordered = []
    try:
        sorted_calls = sorted(tool_calls, key=lambda c: (c.get('iteration') if c.get('iteration') is not None else 0, c.get('index') if c.get('index') is not None else 0))
    except Exception:
        sorted_calls = tool_calls
    missing = []
    positions = []
    lowered = response.lower()
    cursor = 0
    out_of_order = False
    for call in sorted_calls:
        name = str(call.get('name') or '').lower()
        if not name:
            continue
        ordered.append(name)
        pos = lowered.find(name, cursor)
        if pos == -1:
            # try search anywhere to distinguish missing vs out-of-order
            anywhere = lowered.find(name)
            if anywhere == -1:
                missing.append(name)
            else:
                out_of_order = True
                positions.append(anywhere)
        else:
            positions.append(pos)
            cursor = pos + len(name)
    if missing:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'audit list missing tool names: ' + ', '.join(missing), 'evidence_refs': []}
    if out_of_order:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'tool names not in chronological order in audit', 'evidence_refs': []}
    # Check retrieved values appear near each tool name
    value_missing = []
    for call in sorted_calls:
        name = str(call.get('name') or '')
        result = call.get('result')
        if result is None or not name:
            continue
        result_str = str(result).strip()
        if not result_str:
            continue
        # Take a short token from the result to look for
        token = result_str.split('\n')[0].strip().strip('"').strip("'")
        if len(token) > 80:
            token = token[:80]
        if not token:
            continue
        if token.lower() not in lowered:
            value_missing.append(name + ':' + token[:30])
    if value_missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'retrieved values missing for: ' + '; '.join(value_missing), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'phrase present and audit list includes each tool in order with values', 'evidence_refs': []}
