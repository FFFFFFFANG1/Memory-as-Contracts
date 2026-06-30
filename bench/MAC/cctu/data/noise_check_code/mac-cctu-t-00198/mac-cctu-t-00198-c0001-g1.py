def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    bad_calls = []
    arg_values = []
    for tc in tool_calls:
        args = tc.get('arguments')
        if isinstance(args, dict):
            n = len(args)
            if n != 1:
                bad_calls.append({'name': tc.get('name'), 'arg_count': n})
            else:
                v = list(args.values())[0]
                arg_values.append((tc.get('name'), v))
        elif args is None:
            bad_calls.append({'name': tc.get('name'), 'arg_count': 0})
        else:
            arg_values.append((tc.get('name'), args))
    if bad_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Tool calls without exactly one argument: {bad_calls}', 'evidence_refs': bad_calls}
    final = trace.get('final_response') or ''
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to inspect', 'evidence_refs': []}
    missing = []
    for name, val in arg_values:
        s = str(val)
        if s and s not in final:
            missing.append({'name': name, 'value': s})
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'Arguments not documented inline before final answer: {missing}', 'evidence_refs': missing}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'All tool calls had a single argument and values appear documented in the response.', 'evidence_refs': [{'tool': n, 'arg': str(v)} for n,v in arg_values]}
