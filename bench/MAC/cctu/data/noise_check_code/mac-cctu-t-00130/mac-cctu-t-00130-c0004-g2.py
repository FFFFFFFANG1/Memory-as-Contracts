def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tcs = trace.get('tool_calls') or []
    retrieval_tools = {'product_and_appliance_specification_retriever','smartphone_specification_retriever','element_information_provider','historical_event_info_combined','universal_weight_calculator'}
    if not tcs:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls to evaluate ordering','evidence_refs':[]}
    # find first retrieval call index
    first_retr = None
    for tc in tcs:
        if tc.get('name') in retrieval_tools:
            first_retr = tc
            break
    if first_retr is None:
        return {'observed_followed': None,'confidence':'unknown','reason':'no retrieval dispatched','evidence_refs':[]}
    first_iter = first_retr.get('iteration', first_retr.get('index', 0))
    # gather assistant text prior to first retrieval
    pre_text = ''
    for step in traj:
        it = step.get('iteration', step.get('index', 0))
        if it is None: it = 0
        if it < first_iter:
            c = step.get('content') or ''
            pre_text += '\n' + c
    pre_low = pre_text.lower()
    clarify_kw = ['confirm','clarif','restate','just to confirm','to make sure','you mentioned','you said','is that correct','want to verify','double-check','double check']
    has_clarify = any(k in pre_low for k in clarify_kw)
    # check for a model-like token (alphanumeric with digits) in pre_text
    has_model_ref = bool(re.search(r'\b[A-Za-z]*\d+[A-Za-z0-9-]*\b', pre_text))
    if has_clarify and has_model_ref:
        return {'observed_followed': True,'confidence':'medium','reason':'assistant restated model and sought confirmation before retrieval','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':'no clarifying restatement of model names before retrieval dispatch','evidence_refs':[]}
