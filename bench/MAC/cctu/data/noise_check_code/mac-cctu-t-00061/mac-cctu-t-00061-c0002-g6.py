def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    location_tools = {'delta_port_locator','local_cuisine_explorer','location_identifier','organization_locator','person_location_finder','port_locator','seafood_origin_locator','stone_origin_locator','supplier_store_linker'}
    lcl_args = []
    corrob_args = []
    for c in calls:
        name = c.get('name') or ''
        args = c.get('arguments') or {}
        blob = ' '.join(str(v) for v in (args.values() if isinstance(args, dict) else [args])).lower()
        if name == 'landmark_country_locator':
            lcl_args.append(blob)
        elif name in location_tools:
            corrob_args.append(blob)
    if not lcl_args:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'landmark_country_locator never called', 'evidence_refs': []}
    if not corrob_args:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no corroborating location tool called', 'evidence_refs': []}
    unmatched = []
    for la in lcl_args:
        tokens = [t for t in re.findall(r"[a-zA-Z]{4,}", la)]
        matched = False
        for ca in corrob_args:
            if any(t in ca for t in tokens):
                matched = True
                break
        if not matched and tokens:
            unmatched.append(la)
    if unmatched:
        return {'observed_followed': False, 'confidence': 'low', 'reason': f'{len(unmatched)} landmark(s) lacking corroborating tool', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'each landmark_country_locator call has a corroborating location tool call', 'evidence_refs': []}
