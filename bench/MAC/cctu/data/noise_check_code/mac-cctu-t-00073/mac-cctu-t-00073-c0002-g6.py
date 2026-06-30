def evaluate(trace):
    import re
    iso_re = re.compile(r'\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b')
    conf_re = re.compile(r'confidence', re.IGNORECASE)
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found in trajectory.', 'evidence_refs': []}
    texts = []
    for step in traj:
        c = step.get('content') if isinstance(step, dict) else None
        if isinstance(c, str):
            texts.append(c)
    final = trace.get('final_response') or ''
    blob = '\n'.join(texts) + '\n' + final
    has_phase = re.search(r'data[_ ]validation', blob, re.IGNORECASE) is not None
    if not has_phase:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No data_validation phase markers found; cannot determine if logging rule applies.', 'evidence_refs': []}
    missing = []
    for tc in tool_calls:
        name = tc.get('name', '?')
        res = tc.get('result')
        res_str = res if isinstance(res, str) else (str(res) if res is not None else '')
        # search around the call in trajectory texts and result
        combined = res_str
        has_iso = bool(iso_re.search(combined)) or bool(iso_re.search(blob))
        has_conf = bool(conf_re.search(combined)) or bool(conf_re.search(blob))
        if not (has_iso and has_conf):
            missing.append({'tool': name, 'iso': has_iso, 'confidence_note': has_conf})
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Some tool observations during data_validation lack ISO-8601 timestamp and/or confidence note.', 'evidence_refs': missing[:5]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Tool observations include ISO-8601 timestamps and confidence notes.', 'evidence_refs': []}
