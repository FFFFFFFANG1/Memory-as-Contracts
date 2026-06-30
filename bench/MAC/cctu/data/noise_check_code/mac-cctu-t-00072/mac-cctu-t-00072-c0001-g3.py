def evaluate(trace):
    import re, json
    traj = trace.get('trajectory') or []
    # Find assistant messages that accompany tool calls (intermediate steps)
    intermediate_texts = []
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content')
        if tcs and content:
            if isinstance(content, str) and content.strip():
                intermediate_texts.append(content.strip())
    # Also consider tool result messages if present as separate steps
    if not intermediate_texts:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No intermediate assistant content found alongside tool calls.', 'evidence_refs': []}
    def is_raw_json_block(text):
        t = text.strip()
        # strip code fences
        m = re.match(r'^```(?:json)?\s*(.*?)\s*```$', t, re.DOTALL)
        if m:
            t = m.group(1).strip()
        try:
            json.loads(t)
            return True
        except Exception:
            return False
    violations = []
    for i, txt in enumerate(intermediate_texts):
        if not is_raw_json_block(txt):
            violations.append({'index': i, 'snippet': txt[:120]})
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'{len(violations)} intermediate step(s) contained narrative rather than raw JSON.', 'evidence_refs': violations}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'All intermediate assistant messages parse as raw JSON blocks.', 'evidence_refs': []}
