def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    reasons = []
    tool_count = len([c for c in tool_calls if c.get('name')])
    if tool_count < 2:
        reasons.append('tool call count ' + str(tool_count) + ' below 2')
    elif tool_count > 3:
        reasons.append('tool call count ' + str(tool_count) + ' above 3')
    stripped = response.rstrip()
    if not stripped:
        reasons.append('empty response')
    elif not stripped.endswith('.'):
        reasons.append('response does not end with a period')
    if 'Difference:' not in response:
        reasons.append('missing keyword "Difference:"')
    else:
        nums = list(re.finditer(r'-?\d[\d,]*(?:\.\d+)?', response))
        if not nums:
            reasons.append('no numerical answer found in response')
        else:
            last_num = nums[-1]
            before = response[:last_num.start()]
            idx = before.rfind('Difference:')
            if idx == -1:
                reasons.append('"Difference:" does not precede the final numerical answer')
            else:
                between = before[idx + len('Difference:'):]
                if re.search(r'\d', between):
                    reasons.append('another number appears between "Difference:" and the final number')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'tool count in [2,3], ends with period, "Difference:" precedes final number', 'evidence_refs': []}
