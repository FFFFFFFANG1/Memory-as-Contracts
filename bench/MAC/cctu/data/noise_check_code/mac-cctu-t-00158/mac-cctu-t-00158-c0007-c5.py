def evaluate(trace):
    import re
    calls = trace.get('tool_calls', []) or []
    priority = {'geographic_feature_info','nearby_mountain_locator'}
    bio = {'biodiversity_info_tool','forest_tree_data_retriever'}
    names = [c.get('name') for c in calls]
    pri_idx = [i for i,n in enumerate(names) if n in priority]
    bio_idx = [i for i,n in enumerate(names) if n in bio]
    order_ok = None
    if pri_idx and bio_idx:
        order_ok = min(pri_idx) < min(bio_idx) and max(pri_idx) <= max(bio_idx) if False else (min(pri_idx) < min(bio_idx))
    elif pri_idx and not bio_idx:
        order_ok = True
    elif bio_idx and not pri_idx:
        order_ok = False
    final = trace.get('final_response','') or ''
    nums = re.findall(r'(\d+(?:[,\d]*)(?:\.\d+)?)\s*(?:m\b|meters|metres|metre|meter)', final, re.IGNORECASE)
    elev_ok = None
    if nums:
        elev_ok = True
        for n in nums:
            try:
                v = float(n.replace(',',''))
            except: 
                continue
            if abs(v - round(v/10)*10) > 1e-6:
                elev_ok = False
                break
    parts = [x for x in [order_ok, elev_ok] if x is not None]
    if not parts:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'no evidence of priority ordering or elevation reporting', 'evidence_refs':[]}
    followed = all(parts)
    return {'observed_followed': followed, 'confidence':'medium', 'reason': f'order_ok={order_ok}, elev_rounded_ok={elev_ok}', 'evidence_refs':[]}
