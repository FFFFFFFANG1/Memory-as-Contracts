def evaluate(trace):
    import re
    calls=[c for c in trace.get('tool_calls',[]) if c.get('name')=='geodesic_distance_calculator']
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No geodesic_distance_calculator calls found','evidence_refs':[]}
    locations=set()
    pairs_called=set()
    for c in calls:
        args=c.get('arguments') or {}
        if not isinstance(args,dict):
            continue
        vals=[]
        for k,v in args.items():
            if isinstance(v,str) and v.strip():
                vals.append(v.strip().lower())
            elif isinstance(v,(list,tuple)) and len(v)==2 and all(isinstance(x,(int,float)) for x in v):
                vals.append(str(tuple(v)))
        if len(vals)>=2:
            a,b=vals[0],vals[1]
            locations.add(a); locations.add(b)
            pairs_called.add(frozenset([a,b]))
    n=len(locations)
    expected=n*(n-1)//2 if n>=2 else 0
    final=(trace.get('final_response') or '').lower()
    referenced=set()
    for loc in locations:
        if loc in final:
            referenced.add(loc)
    # use locations from tool args as proxy for referenced locations
    target_locs = referenced if len(referenced)>=2 else locations
    m=len(target_locs)
    needed_pairs={frozenset([a,b]) for a in target_locs for b in target_locs if a<b}
    missing=needed_pairs-pairs_called
    if missing:
        return {'observed_followed': False,'confidence':'medium','reason': f'Missing geodesic calls for {len(missing)} of {len(needed_pairs)} location pairs','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'medium','reason': f'All {len(needed_pairs)} pairs among {m} locations covered by geodesic_distance_calculator','evidence_refs':[]}
