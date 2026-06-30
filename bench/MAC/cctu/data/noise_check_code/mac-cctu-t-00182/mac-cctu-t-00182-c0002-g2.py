def evaluate(trace):
    tcs = trace.get('tool_calls') or []
    if len(tcs) < 2:
        return {'observed_followed': None, 'confidence':'unknown','reason':'insufficient tool calls','evidence_refs':[]}
    traj = trace.get('trajectory') or []
    for step in traj:
        calls = step.get('tool_calls') or []
        if len(calls) > 1:
            return {'observed_followed': False,'confidence':'high','reason':'parallel tool calls in one step','evidence_refs':[{'step_calls':len(calls)}]}
    prev_out = None
    for i, c in enumerate(tcs):
        args = c.get('arguments') or {}
        if i > 0:
            if prev_out is None:
                return {'observed_followed': None,'confidence':'low','reason':'previous output unavailable','evidence_refs':[{'index':i}]}
            vals = []
            if isinstance(args, dict):
                vals = [str(v) for v in args.values()]
            else:
                vals = [str(args)]
            prev_str = str(prev_out)
            if not any(v.strip() == prev_str.strip() for v in vals):
                return {'observed_followed': False,'confidence':'high','reason':f'call {i} args do not match prior exact output','evidence_refs':[{'index':i,'args':args,'prev_out':prev_str[:200]}]}
        prev_out = c.get('result')
    return {'observed_followed': True,'confidence':'high','reason':'sequential, each call consumed prior exact output','evidence_refs':[]}
