def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    trajectory = trace.get('trajectory') or []
    if not response.strip() and not tool_calls and not trajectory:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    tool_count = len([c for c in tool_calls if c.get('name')])
    if tool_count == 0:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls but constraint requires 5-10', 'evidence_refs': []}
    if tool_count < 5 or tool_count > 10:
        reasons.append('tool_count=' + str(tool_count) + ' not in [5,10]')
    turn_count = len(trajectory)
    if turn_count and (turn_count < 5 or turn_count > 12):
        reasons.append('turns=' + str(turn_count) + ' not in [5,12]')
    word_count = len(response.split())
    if word_count == 0:
        reasons.append('response text missing')
    elif word_count > 100:
        reasons.append('response exceeds 100 words: ' + str(word_count))
    pattern = re.compile(r'The local fish in the area is:\s*\S+\.?\s*$')
    if not pattern.search(response.strip()):
        reasons.append('final phrase "The local fish in the area is: [Species]" not found at end')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'tool count, turns, length, and ending phrase satisfied', 'evidence_refs': []}
