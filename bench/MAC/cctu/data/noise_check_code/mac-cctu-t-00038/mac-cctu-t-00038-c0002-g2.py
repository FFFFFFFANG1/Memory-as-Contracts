def evaluate(trace):
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    reasons = []
    if not response.strip() and not tool_calls and not trajectory:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no observable behavior', 'evidence_refs': []}
    # Check [Answer] identifier in response
    has_identifier = '[Answer]' in response
    if not has_identifier:
        reasons.append('missing [Answer] identifier in final response')
    else:
        idx = response.rfind('[Answer]')
        after = response[idx+len('[Answer]'):].strip()
        if not after:
            reasons.append('[Answer] identifier not followed by an answer')
    # Tool call count <= 3
    tc_count = len(tool_calls)
    if tc_count > 3:
        reasons.append('tool calls ' + str(tc_count) + ' exceed 3')
    # Interaction rounds: count assistant steps in trajectory
    rounds = 0
    for step in trajectory:
        if isinstance(step, dict):
            role = step.get('role') or step.get('type') or ''
            if role in ('assistant','model','agent') or 'tool_calls' in step or 'content' in step:
                rounds += 1
        else:
            rounds += 1
    if rounds == 0:
        rounds = len(trajectory)
    if rounds < 2 or rounds > 5:
        reasons.append('interaction rounds ' + str(rounds) + ' outside [2,5]')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': '[Answer] identifier present, tool calls <=3, rounds within [2,5]', 'evidence_refs': []}
