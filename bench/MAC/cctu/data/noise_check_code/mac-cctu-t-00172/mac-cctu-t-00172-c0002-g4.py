def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls to annotate.', 'evidence_refs': []}
    traj = trace.get('trajectory') or []
    final = trace.get('final_response') or ''
    texts = []
    for step in traj:
        c = step.get('content') if isinstance(step, dict) else None
        if c: texts.append(str(c))
    texts.append(final)
    blob = '\n'.join(texts).lower()
    if 'evidence annotation' not in blob and 'evidence-annotation' not in blob:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No Evidence Annotation section detected; cannot verify provenance pairing.', 'evidence_refs': []}
    # Extract evidence annotation section
    m = re.search(r'evidence annotation[\s\S]*', blob)
    section = m.group(0) if m else blob
    missing = []
    for tc in tool_calls:
        name = (tc.get('name') or '').lower()
        if not name: continue
        has_tool = name in section
        # check sub-question indicator near tool mention
        has_subq = bool(re.search(r'sub[- ]?question|sq\s*\d|q\d|supports', section))
        if not (has_tool and has_subq):
            missing.append(name)
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Missing provenance pairing for tools: {sorted(set(missing))}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Each tool observation appears paired with tool name and sub-question reference in Evidence Annotation.', 'evidence_refs': []}
