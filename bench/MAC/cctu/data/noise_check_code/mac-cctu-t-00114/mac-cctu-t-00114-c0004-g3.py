def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    forbidden = {'altitude_tool', 'geometry_tool'}
    intake_tool = 'historical_event_info_retriever'
    saw_intake = False
    violations = []
    for i, c in enumerate(calls):
        name = c.get('name') or c.get('tool_name') or ''
        if name == intake_tool:
            saw_intake = True
        elif name in forbidden and not saw_intake:
            violations.append({'index': i, 'tool': name})
    if violations:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'forbidden tool(s) called before any {intake_tool} disambiguation: {violations}', 'evidence_refs': violations}
    if not saw_intake:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'intake retriever never used; phase unclear', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'altitude_tool/geometry_tool not invoked before historical_event_info_retriever', 'evidence_refs': []}
