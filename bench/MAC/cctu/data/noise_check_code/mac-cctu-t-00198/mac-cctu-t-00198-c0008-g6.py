def evaluate(trace):
    import re
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    def failed(c):
        r = c.get('result')
        if r is None: return False
        s = str(r).lower()
        return any(k in s for k in ['error','failed','failure','exception','not found','invalid','timeout'])
    # group consecutive calls by tool name
    failures = [i for i,c in enumerate(calls) if failed(c)]
    if not failures:
        return {'observed_followed': None,'confidence':'unknown','reason':'no failed tool calls observed; constraint not triggered','evidence_refs':[]}
    refs = []
    retries_seen = False
    fallback_or_limit_ok = True
    for idx in failures:
        c = calls[idx]
        name = c.get('name')
        args = c.get('arguments')
        # count subsequent same-tool retries with different args
        retry_count = 0
        j = idx + 1
        last_args = args
        while j < len(calls) and calls[j].get('name') == name:
            if calls[j].get('arguments') != last_args:
                retry_count += 1
                retries_seen = True
                last_args = calls[j].get('arguments')
            if not failed(calls[j]):
                break
            j += 1
        if retry_count > 3:
            fallback_or_limit_ok = False
            refs.append({'index': idx, 'retries': retry_count})
        # after retries, check fallback to alternative tool if still failing
        if j < len(calls) and failed(calls[j-1]) if j>idx else False:
            if j < len(calls) and calls[j].get('name') == name:
                fallback_or_limit_ok = False
    notes = (trace.get('final_response') or '')
    for step in trace.get('trajectory') or []:
        notes += ' ' + str(step.get('content') or '')
    notes_l = notes.lower()
    logged = any(k in notes_l for k in ['retry','retried','attempt','retrying'])
    if not retries_seen:
        return {'observed_followed': False,'confidence':'medium','reason':'failed calls present but no retries with adjusted parameters observed','evidence_refs':refs}
    if not fallback_or_limit_ok:
        return {'observed_followed': False,'confidence':'medium','reason':'retry policy exceeded or no fallback','evidence_refs':refs}
    if not logged:
        return {'observed_followed': False,'confidence':'low','reason':'no retry log in working notes','evidence_refs':refs}
    return {'observed_followed': True,'confidence':'medium','reason':'retries with adjusted params within limit and logged','evidence_refs':refs}
