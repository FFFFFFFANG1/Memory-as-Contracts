def evaluate(trace):
    response = trace.get('final_response')
    tool_calls = trace.get('tool_calls') or []
    if response is None and not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no observable behavior', 'evidence_refs': []}
    response = str(response or '')
    names = [str(c.get('name') or '') for c in tool_calls]
    phf_count = sum(1 for n in names if n == 'political_history_finder')
    reasons = []
    if phf_count != 1:
        reasons.append('political_history_finder called ' + str(phf_count) + ' times (expected exactly 1)')
    stripped = response.rstrip()
    if len(response) >= 50:
        reasons.append('response length ' + str(len(response)) + ' >= 50 chars')
    if not stripped:
        reasons.append('response is empty')
    else:
        last = stripped[-1]
        if last in '.!?,;:。！？，；：':
            reasons.append('response ends with terminating punctuation: ' + repr(last))
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'exactly one political_history_finder call; response under 50 chars without terminating punctuation', 'evidence_refs': []}
