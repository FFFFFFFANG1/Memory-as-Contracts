def evaluate(trace):
    traj = trace.get('trajectory') or []
    final = trace.get('final_response') or ''
    tool_calls = trace.get('tool_calls') or []
    # Constraint is permissive: drafting from background knowledge before tool verification is allowed.
    # Check whether assistant produced any pre-tool textual draft, or used election tool at all.
    pre_tool_text = False
    saw_tool = False
    for step in traj:
        content = (step.get('content') or '').strip() if isinstance(step, dict) else ''
        calls = step.get('tool_calls') or [] if isinstance(step, dict) else []
        if not saw_tool and content:
            pre_tool_text = True
        if calls:
            saw_tool = True
    used_election_tool = any((tc.get('name') == 'election_result_analyzer') for tc in tool_calls)
    # Permissive constraint: if there is a draft before tools, or no violation pattern, mark followed.
    if pre_tool_text or used_election_tool or final:
        return {'observed_followed': True, 'confidence': 'low', 'reason': 'Permissive constraint; drafting before verification is allowed and trajectory is consistent.', 'evidence_refs': []}
    return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'Insufficient evidence to evaluate permissive drafting constraint.', 'evidence_refs': []}
