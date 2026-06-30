def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    final = trace.get('final_response') or ''
    # Gather all textual content from assistant steps in order
    texts = []
    for step in traj:
        c = step.get('content') or ''
        if c:
            texts.append(c)
    blob = '\n'.join(texts) + '\n' + final
    manifest_pat = re.compile(r'manifest', re.I)
    has_manifest_mention = bool(manifest_pat.search(blob))
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls invoked; cannot verify manifest-before-invoke behavior.', 'evidence_refs': []}
    if not has_manifest_mention:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Tools were called but no manifest log of tool names/parameter signatures is present in trajectory.', 'evidence_refs': [{'tool_calls_count': len(tool_calls)}]}
    # Check each tool call name appears in text prior to its invocation
    missing = []
    seen_text = ''
    text_idx = 0
    # Build a per-step concatenation tracker by iteration index
    step_texts = [(step.get('content') or '') for step in traj]
    for tc in tool_calls:
        name = tc.get('name') or ''
        it = tc.get('iteration')
        prior = '\n'.join(step_texts[:it]) if isinstance(it, int) else blob
        if name and name not in prior:
            missing.append(name)
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Tools invoked without prior manifest entry: {sorted(set(missing))}.', 'evidence_refs': [{'missing': sorted(set(missing))}]}
    return {'observed_followed': True, 'confidence': 'low', 'reason': 'Manifest references found and each invoked tool name appeared in prior trajectory text.', 'evidence_refs': []}
