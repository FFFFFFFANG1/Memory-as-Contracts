def evaluate(trace):
    import re, json
    tool_calls = trace.get('tool_calls', []) or []
    traj = trace.get('trajectory', []) or []
    final = trace.get('final_response', '') or ''
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls to log', 'evidence_refs': []}
    # Collect assistant content prior to final response
    pre_texts = []
    for step in traj:
        c = step.get('content') if isinstance(step, dict) else None
        if c:
            pre_texts.append(str(c))
    combined = '\n'.join(pre_texts)
    # Find JSON-like objects in combined text
    candidates = re.findall(r'\{[^{}]*\}', combined, flags=re.DOTALL)
    parsed = []
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                parsed.append(obj)
        except Exception:
            pass
    def has_fields(obj):
        keys = {k.lower() for k in obj.keys()}
        name_ok = any('tool' in k or 'name' in k for k in keys)
        param_ok = any('param' in k or 'arg' in k or 'input' in k for k in keys)
        ts_ok = any('time' in k or 'stamp' in k or 'date' in k for k in keys)
        return name_ok and param_ok and ts_ok
    valid_logs = [o for o in parsed if has_fields(o)]
    needed = len(tool_calls)
    if len(valid_logs) >= needed:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': f'found {len(valid_logs)} JSON log entries for {needed} tool calls', 'evidence_refs': []}
    if not valid_logs:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no structured JSON log entries with name/params/timestamp found before user-facing text', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'only {len(valid_logs)} valid log entries vs {needed} tool calls', 'evidence_refs': []}
