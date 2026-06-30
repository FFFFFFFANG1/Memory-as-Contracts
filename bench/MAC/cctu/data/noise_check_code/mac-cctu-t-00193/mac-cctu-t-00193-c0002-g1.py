def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    ts_pat = re.compile(r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}|\d{2}:\d{2}:\d{2}|\d{2}:\d{2}|timestamp|\bT\d{2}:\d{2})', re.I)
    # Build running log of assistant text up to each step
    logged_calls = []
    running_text = ''
    missing = []
    for step in traj:
        content = step.get('content') or ''
        calls = step.get('tool_calls') or []
        # text in this step BEFORE its tool calls counts as pre-log
        pre_text = running_text + '\n' + content
        for c in calls:
            name = (c.get('name') or c.get('function',{}).get('name') or '').strip()
            if not name:
                continue
            has_name = name.lower() in pre_text.lower()
            has_ts = bool(ts_pat.search(pre_text))
            logged_calls.append((name, has_name, has_ts))
            if not (has_name and has_ts):
                missing.append(name)
        running_text = pre_text
    if not logged_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'could not associate calls with trajectory steps', 'evidence_refs': []}
    followed = len(missing) == 0
    return {'observed_followed': followed, 'confidence': 'medium', 'reason': ('all tool invocations pre-logged with name and timestamp' if followed else f'missing pre-log name/timestamp for: {missing}'), 'evidence_refs': []}
