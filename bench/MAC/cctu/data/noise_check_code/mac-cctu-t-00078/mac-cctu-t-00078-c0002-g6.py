def evaluate(trace):
    import re
    final=(trace.get('final_response') or '')
    tcs=trace.get('tool_calls') or []
    if not tcs:
        return {'observed_followed':None,'confidence':'unknown','reason':'no tool calls to summarize','evidence_refs':[]}
    low=final.lower()
    pm_markers=['post-mortem','post mortem','postmortem','retrospective','retro log','review phase']
    has_phase=any(m in low for m in pm_markers)
    if not has_phase:
        return {'observed_followed':False,'confidence':'medium','reason':'no post-mortem/retrospective section found in final response','evidence_refs':[]}
    tool_names=[]
    for t in tcs:
        n=t.get('name')
        if n and n not in tool_names:
            tool_names.append(n)
    missing=[n for n in tool_names if n.lower() not in low and n.replace('_',' ').lower() not in low]
    flag_terms=['unverified','unconfirmed','not verified','cannot verify','assumption','caveat','limitation','flag']
    flagged=any(term in low for term in flag_terms)
    if missing:
        return {'observed_followed':False,'confidence':'medium','reason':f'retrospective missing summary for tools: {missing}','evidence_refs':[]}
    if not flagged:
        return {'observed_followed':False,'confidence':'low','reason':'no flagging of unverified claims detected','evidence_refs':[]}
    return {'observed_followed':True,'confidence':'medium','reason':'retrospective summarizes tools and flags unverified claims','evidence_refs':[]}
