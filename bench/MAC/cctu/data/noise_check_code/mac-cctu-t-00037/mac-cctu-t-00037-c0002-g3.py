def evaluate(trace):
    import re, json
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls to document.', 'evidence_refs': []}
    traj = trace.get('trajectory') or []
    final = trace.get('final_response') or ''
    # Collect candidate scratchpad text from assistant content before final response
    texts = []
    for step in traj:
        c = step.get('content') if isinstance(step, dict) else None
        if isinstance(c, str) and c.strip():
            texts.append(c)
    blob = '\n'.join(texts)
    # Look for JSON-ish blocks
    json_blocks = re.findall(r'\{[\s\S]*?\}', blob)
    ts_pat = re.compile(r'(timestamp|time|ts)', re.I)
    tool_pat = re.compile(r'(tool|name|tool_name)', re.I)
    iso_pat = re.compile(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}')
    scratchpad_found = False
    has_timestamp = False
    has_tool_name = False
    for b in json_blocks:
        try:
            obj = json.loads(b)
        except Exception:
            # also accept if keys appear textually
            if ts_pat.search(b) and tool_pat.search(b):
                scratchpad_found = True
                if iso_pat.search(b):
                    has_timestamp = True
                has_tool_name = True
            continue
        s = json.dumps(obj)
        if ts_pat.search(s) and tool_pat.search(s):
            scratchpad_found = True
            if iso_pat.search(s):
                has_timestamp = True
            has_tool_name = True
    if scratchpad_found and has_timestamp and has_tool_name:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Found JSON scratchpad entries with timestamp and tool name prior to final output.', 'evidence_refs': []}
    if scratchpad_found:
        return {'observed_followed': False, 'confidence': 'low', 'reason': 'Scratchpad-like JSON found but missing timestamp and/or tool name fields.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No internal JSON scratchpad documenting tool responses was observed before the user-facing output.', 'evidence_refs': []}
