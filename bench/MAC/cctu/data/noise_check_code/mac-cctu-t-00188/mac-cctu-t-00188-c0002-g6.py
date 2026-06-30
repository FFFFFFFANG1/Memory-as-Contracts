def evaluate(trace):
    tcs = trace.get('tool_calls') or []
    if not tcs:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    # find first call to biographical_info_retriever
    bio_idx = None
    for i,tc in enumerate(tcs):
        if tc.get('name') == 'biographical_info_retriever':
            bio_idx = i
            break
    if bio_idx is None:
        return {'observed_followed': None, 'confidence':'unknown','reason':'biographical_info_retriever not invoked; cannot tell if biography was needed','evidence_refs':[]}
    # must be the first tool called
    if bio_idx != 0:
        return {'observed_followed': False,'confidence':'high','reason':f'biographical_info_retriever was not the first tool (index {bio_idx})','evidence_refs':[tcs[0].get('name')]}
    # must be alone in its iteration/parallel group
    first = tcs[0]
    it = first.get('iteration')
    same_iter = [t for t in tcs if t.get('iteration') == it]
    if len(same_iter) > 1:
        names = [t.get('name') for t in same_iter]
        return {'observed_followed': False,'confidence':'high','reason':f'biographical_info_retriever invoked in parallel with: {names}','evidence_refs':names}
    return {'observed_followed': True,'confidence':'high','reason':'biographical_info_retriever invoked alone first','evidence_refs':['biographical_info_retriever']}
