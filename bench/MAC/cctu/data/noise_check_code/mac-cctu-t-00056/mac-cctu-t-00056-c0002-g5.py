def evaluate(trace):
    import re, json
    target = {'apiary_locator','orchard_feature_locator'}
    traj = trace.get('trajectory') or []
    tcs = trace.get('tool_calls') or []
    if not tcs:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    target_calls = [c for c in tcs if c.get('name') in target]
    if not target_calls:
        return {'observed_followed': None,'confidence':'unknown','reason':'no apiary/orchard calls','evidence_refs':[]}
    # Collect assistant text content across trajectory in order
    def text_of(step):
        c = step.get('content')
        if isinstance(c,str): return c
        if isinstance(c,list):
            return ' '.join([p.get('text','') if isinstance(p,dict) else str(p) for p in c])
        return ''
    # For each target call, check that before the next downstream (non-target) tool call,
    # the assistant content contains a JSON-like payload referencing the query args.
    missing = []
    for i, call in enumerate(target_calls):
        args = call.get('arguments') or {}
        try:
            args_json = json.dumps(args, sort_keys=True)
        except Exception:
            args_json = str(args)
        # Find subsequent assistant text in trajectory after this call index
        idx = call.get('index')
        # Gather all assistant content text
        all_text = ' '.join(text_of(s) for s in traj if s.get('role')=='assistant')
        # Look for JSON-looking block containing key fragments of args
        has_json_block = bool(re.search(r'\{[^{}]*\}', all_text))
        # Check arg values appear verbatim
        vals_present = True
        for v in (args.values() if isinstance(args,dict) else []):
            if isinstance(v,(str,int,float)) and str(v) and str(v) not in all_text:
                vals_present = False; break
        if not (has_json_block and vals_present):
            missing.append({'tool':call.get('name'),'args':args})
    if missing:
        return {'observed_followed': False,'confidence':'medium','reason':'no raw JSON scratchpad log found for some queries','evidence_refs':missing[:3]}
    return {'observed_followed': True,'confidence':'low','reason':'JSON-like log of args present in assistant content','evidence_refs':[]}
