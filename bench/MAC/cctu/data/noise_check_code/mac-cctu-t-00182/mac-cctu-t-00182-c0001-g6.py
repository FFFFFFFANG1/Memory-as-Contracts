def evaluate(trace):
    tool_calls = trace.get('tool_calls') or []
    final = (trace.get('final_response') or '').strip()
    n = len(tool_calls)
    traj = trace.get('trajectory') or []
    # Heuristic: internal knowledge first means the agent should produce substantive answer with few/no tool calls used as spot checks.
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to evaluate.', 'evidence_refs': []}
    if n == 0:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'No tools invoked; agent relied on internal knowledge.', 'evidence_refs': []}
    # Count assistant content length before first tool call to see if internal reasoning happened
    pre_tool_text = 0
    saw_tool = False
    for step in traj:
        tcs = step.get('tool_calls') or []
        content = step.get('content') or ''
        if not saw_tool:
            pre_tool_text += len(content or '')
        if tcs:
            saw_tool = True
    # Spot-check pattern: small number of tool calls relative to a substantive answer
    if n <= 3 and len(final) > 100:
        return {'observed_followed': True, 'confidence': 'low', 'reason': f'{n} tool call(s) used as apparent spot-checks alongside substantive response.', 'evidence_refs': [f'tool_calls={n}']}
    if n > 5:
        return {'observed_followed': False, 'confidence': 'low', 'reason': f'{n} tool calls suggests tool-first rather than internal-knowledge-first behavior.', 'evidence_refs': [f'tool_calls={n}']}
    return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Cannot reliably determine reliance on internal knowledge from trace.', 'evidence_refs': [f'tool_calls={n}']}
