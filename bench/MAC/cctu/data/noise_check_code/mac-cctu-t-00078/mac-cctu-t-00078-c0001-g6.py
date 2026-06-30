def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'No tool calls; sub-task structure unclear','evidence_refs':[]}
    text_blobs = [final]
    for step in traj:
        c = step.get('content') if isinstance(step, dict) else None
        if c: text_blobs.append(c)
    joined = '\n'.join(text_blobs).lower()
    summary_kw = ['summary','summariz','reflect','recap','in summary','to summarize','overview of findings']
    uncertainty_kw = ['uncertain','remaining question','still unknown','unclear','open question','limitation','caveat','not enough','unable to','could not determine','further research']
    has_summary = any(k in joined for k in summary_kw)
    has_uncert = any(k in joined for k in uncertainty_kw)
    if has_summary and has_uncert:
        return {'observed_followed': True,'confidence':'medium','reason':'Found reflection-style summary and uncertainty acknowledgement','evidence_refs':[]}
    if has_summary and not has_uncert:
        return {'observed_followed': False,'confidence':'low','reason':'Summary present but no remaining uncertainties noted','evidence_refs':[]}
    if not has_summary and has_uncert:
        return {'observed_followed': False,'confidence':'low','reason':'Uncertainty mentioned but no explicit summary/reflection','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':'No written reflection summarizing tool outputs or uncertainties detected','evidence_refs':[]}
