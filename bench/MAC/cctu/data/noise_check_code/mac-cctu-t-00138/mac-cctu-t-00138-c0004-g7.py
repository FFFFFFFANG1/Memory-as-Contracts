def evaluate(trace):
    import re
    calls=[c for c in trace.get('tool_calls',[]) if c.get('name')=='elevation_finder']
    if not calls:
        return {'observed_followed':None,'confidence':'unknown','reason':'no elevation_finder calls','evidence_refs':[]}
    final=trace.get('final_response') or ''
    if not final:
        return {'observed_followed':None,'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    # extract numeric outputs from each call result
    nums=[]
    for c in calls:
        r=c.get('result')
        s=r if isinstance(r,str) else str(r)
        found=re.findall(r'-?\d+\.?\d*',s or '')
        nums.append(found)
    # check that each call has at least one of its numbers appearing in final
    missing=[]
    for i,fs in enumerate(nums):
        if not fs:
            continue
        if not any(n in final for n in fs):
            missing.append(i)
    if missing:
        return {'observed_followed':False,'confidence':'medium','reason':f'missing raw outputs for calls {missing}','evidence_refs':[]}
    # check for a provenance-log-like section
    low=final.lower()
    has_log=any(k in low for k in ['provenance','log','elevation_finder','raw output','invocation'])
    if not has_log:
        return {'observed_followed':False,'confidence':'low','reason':'no provenance log section found','evidence_refs':[]}
    # check ordering: provenance log appears before comparison/synthesis
    log_idx=-1
    for k in ['provenance','raw output','invocation log','elevation_finder call']:
        j=low.find(k)
        if j>=0 and (log_idx<0 or j<log_idx):
            log_idx=j
    cmp_idx=-1
    for k in ['comparison','compared','higher than','lower than','taller','synthesis','in summary','overall']:
        j=low.find(k)
        if j>=0 and (cmp_idx<0 or j<cmp_idx):
            cmp_idx=j
    if log_idx>=0 and cmp_idx>=0 and log_idx>cmp_idx:
        return {'observed_followed':False,'confidence':'medium','reason':'comparison appears before provenance log','evidence_refs':[]}
    return {'observed_followed':True,'confidence':'medium','reason':'provenance log present with raw outputs before comparison','evidence_refs':[]}
