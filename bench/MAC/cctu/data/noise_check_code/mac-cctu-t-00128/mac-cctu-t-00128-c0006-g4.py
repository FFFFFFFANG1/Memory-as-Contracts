def evaluate(trace):
    import re
    final=(trace.get('final_response') or '')
    tcs=trace.get('tool_calls') or []
    # Detect depth figures in final response (numbers with depth units or near 'depth')
    depth_pat=re.compile(r'(\d[\d,\.]*)\s*(m|meters|metres|ft|feet|km|kilometers)\b',re.I)
    has_depth_fig=False
    for m in depth_pat.finditer(final):
        # check context for 'depth' within +/-40 chars
        s=max(0,m.start()-40); e=min(len(final),m.end()+40)
        if re.search(r'depth|deep|seabed|bathymetr',final[s:e],re.I):
            has_depth_fig=True; break
    if not has_depth_fig and re.search(r'depth',final,re.I):
        # depth mentioned with numbers anywhere
        if re.search(r'depth[^\n]{0,60}\d',final,re.I) or re.search(r'\d[^\n]{0,60}depth',final,re.I):
            has_depth_fig=True
    if not has_depth_fig:
        return {'observed_followed':None,'confidence':'low','reason':'No depth figure detected in final response; cannot assess cross-verification.','evidence_refs':[]}
    depth_tools={'ocean_depth_analyzer','geographical_feature_measurement','factual_data_retriever'}
    used=[tc for tc in tcs if (tc.get('name') in depth_tools)]
    names=set(tc.get('name') for tc in used)
    if len(names)>=2 or len(used)>=2:
        return {'observed_followed':True,'confidence':'medium','reason':f'Depth figure present and {len(used)} depth-relevant tool calls across {len(names)} distinct tools provide cross-verification.','evidence_refs':[tc.get('name') for tc in used]}
    return {'observed_followed':False,'confidence':'medium','reason':f'Depth figure present but only {len(used)} depth-relevant tool invocation(s); two independent verifications not evidenced.','evidence_refs':[tc.get('name') for tc in used]}
