def evaluate(trace):
    import re
    final = (trace.get('final_response') or '').strip()
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls to verify against', 'evidence_refs': []}
    if not final:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'empty final response', 'evidence_refs': []}
    lines = [l.rstrip() for l in final.splitlines() if l.strip()]
    if not lines:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no content lines', 'evidence_refs': []}
    bullet_re = re.compile(r'^\s*([-*+\u2022]|\d+[.)])\s+')
    trailing = []
    for line in reversed(lines):
        if bullet_re.match(line):
            trailing.append(line)
        else:
            break
    if len(trailing) < len(tool_calls):
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'trailing bullet count {len(trailing)} < tool calls {len(tool_calls)}', 'evidence_refs': []}
    trailing_text = '\n'.join(trailing)
    missing_names = []
    missing_outputs = []
    for tc in tool_calls:
        name = (tc.get('name') or '').strip()
        if name and name not in trailing_text:
            missing_names.append(name)
        result = tc.get('result')
        if result is None:
            continue
        rstr = str(result).strip()
        if not rstr:
            continue
        snippet = rstr[:40]
        if snippet and snippet not in trailing_text:
            missing_outputs.append(snippet)
    if missing_names or missing_outputs:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'missing names={missing_names} missing outputs={missing_outputs}', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'final ends with bullets covering all tools and outputs', 'evidence_refs': []}
