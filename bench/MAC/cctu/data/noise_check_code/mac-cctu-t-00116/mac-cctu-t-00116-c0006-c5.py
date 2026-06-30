def evaluate(trace):
    trajectory = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls observed; constraint presupposes tool usage with one-call-per-turn discipline', 'evidence_refs': []}
    offenders = []
    saw_any_step_with_calls = False
    for idx, step in enumerate(trajectory):
        if not isinstance(step, dict):
            continue
        calls = step.get('tool_calls') or []
        if not isinstance(calls, list):
            continue
        if len(calls) >= 1:
            saw_any_step_with_calls = True
        if len(calls) > 1:
            names = [str(c.get('name') or '') for c in calls if isinstance(c, dict)]
            offenders.append({'step_index': idx, 'count': len(calls), 'tools': names})
    if offenders:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'one or more turns issued multiple tool calls in parallel', 'evidence_refs': offenders}
    if not saw_any_step_with_calls:
        # tool_calls present but not attributable to a turn; cannot verify per-turn discipline
        iterations = sorted({c.get('iteration') for c in tool_calls if isinstance(c, dict) and c.get('iteration') is not None})
        if iterations:
            from collections import Counter
            counts = Counter(c.get('iteration') for c in tool_calls if isinstance(c, dict))
            over = [it for it, n in counts.items() if n > 1]
            if over:
                return {'observed_followed': False, 'confidence': 'medium', 'reason': 'multiple tool calls share the same iteration/turn', 'evidence_refs': [{'iterations': over}]}
            return {'observed_followed': True, 'confidence': 'medium', 'reason': 'each iteration carries at most one tool call', 'evidence_refs': []}
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'cannot determine per-turn grouping of tool calls', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'every turn issued at most one tool call', 'evidence_refs': []}
