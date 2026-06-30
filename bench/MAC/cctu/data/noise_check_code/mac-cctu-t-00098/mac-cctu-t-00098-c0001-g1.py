def evaluate(trace):
    response = str(trace.get('final_response') or '')
    trajectory = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not trajectory and not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    round_count = len(trajectory)
    if round_count < 8:
        reasons.append('interaction rounds ' + str(round_count) + ' below 8')
    elif round_count > 13:
        reasons.append('interaction rounds ' + str(round_count) + ' above 13')
    tc_count = len(tool_calls)
    if tc_count < 7:
        reasons.append('tool calls ' + str(tc_count) + ' below 7')
    elif tc_count > 12:
        reasons.append('tool calls ' + str(tc_count) + ' above 12')
    has_chain = '[Chain of Relationships]' in response
    has_final = '[Final Answer]' in response
    if not has_chain:
        reasons.append('missing [Chain of Relationships] marker')
    if not has_final:
        reasons.append('missing [Final Answer] marker')
    if has_chain and has_final:
        if response.find('[Chain of Relationships]') > response.find('[Final Answer]'):
            reasons.append('[Chain of Relationships] must appear before [Final Answer]')
        tail = response.rstrip()
        idx = tail.rfind('[Final Answer]')
        if idx == -1 or len(tail[idx:].strip()) < len('[Final Answer]') + 1:
            pass
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'turn count, tool call count, and end markers satisfied', 'evidence_refs': []}
