def evaluate(trace):
    import re
    final = trace.get('final_response') or ''
    tool_calls = trace.get('tool_calls') or []
    if not final.strip():
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Empty final response', 'evidence_refs': []}
    paragraphs = [p for p in re.split(r'\n\s*\n', final.strip()) if p.strip()]
    multi_para = len(paragraphs) >= 2
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls in trajectory to verify listing', 'evidence_refs': []}
    missing_names = []
    missing_outputs = []
    low = final.lower()
    for tc in tool_calls:
        name = (tc.get('name') or '').lower()
        if name and name not in low:
            missing_names.append(name)
        result = tc.get('result')
        if result is None:
            continue
        rstr = str(result).strip()
        if not rstr:
            continue
        # Check if some distinctive substring of result appears
        snippet = rstr[:40]
        # try a few tokens
        tokens = [t for t in re.findall(r'[A-Za-z0-9]{4,}', rstr)][:5]
        found = snippet in final or any(t in final for t in tokens)
        if not found:
            missing_outputs.append(name or 'tool')
    followed = multi_para and not missing_names and not missing_outputs
    reason_parts = []
    if not multi_para:
        reason_parts.append(f'Only {len(paragraphs)} paragraph(s)')
    if missing_names:
        reason_parts.append('Missing tool names: ' + ','.join(missing_names))
    if missing_outputs:
        reason_parts.append('Missing raw outputs for: ' + ','.join(missing_outputs))
    if followed:
        reason_parts.append('Multi-paragraph response lists all tool invocations and outputs')
    return {'observed_followed': followed, 'confidence': 'medium', 'reason': '; '.join(reason_parts), 'evidence_refs': []}
