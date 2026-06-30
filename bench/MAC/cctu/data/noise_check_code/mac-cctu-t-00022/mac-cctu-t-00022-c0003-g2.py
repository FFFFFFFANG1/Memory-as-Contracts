def evaluate(trace):
    import re
    allowed = {'political_term_tracker','election_result_finder'}
    traj = trace.get('trajectory') or []
    tcs = trace.get('tool_calls') or []
    if not tcs:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    # Find first non-allowed tool call index
    first_other = None
    for tc in tcs:
        if tc.get('name') not in allowed:
            first_other = tc
            break
    memo_pat = re.compile(r'scope\s*memo|scoping\s*memo|\bscope\b.*\bmemo\b', re.I)
    # Look in assistant text content prior to any tool call (scoping phase outputs)
    memo_found_before_other = False
    memo_found_anywhere = False
    # iterate trajectory in order
    for step in traj:
        content = step.get('content') or ''
        if isinstance(content, list):
            content = ' '.join([c.get('text','') if isinstance(c,dict) else str(c) for c in content])
        if memo_pat.search(content or ''):
            memo_found_anywhere = True
            if first_other is None:
                memo_found_before_other = True
            else:
                # check this step came before first_other tool call
                step_calls = step.get('tool_calls') or []
                # if step has no other-tool call yet, memo is before
                has_other = any((tc.get('name') if isinstance(tc,dict) else None) not in allowed and (tc.get('name') if isinstance(tc,dict) else None) is not None for tc in step_calls)
                if not has_other:
                    memo_found_before_other = True
                break
    if first_other is None:
        # All tool calls were within allowed set; need memo somewhere in scoping
        if memo_found_anywhere:
            return {'observed_followed': True, 'confidence':'medium','reason':'only allowed tools used; scope memo present','evidence_refs':[]}
        return {'observed_followed': None, 'confidence':'low','reason':'only allowed tools used but no explicit scope memo detected','evidence_refs':[]}
    # A non-allowed tool was invoked
    if not memo_found_before_other:
        return {'observed_followed': False, 'confidence':'high','reason':f"non-allowed tool {first_other.get('name')} invoked without a prior written scope memo",'evidence_refs':[str(first_other)]}
    return {'observed_followed': True, 'confidence':'medium','reason':'scope memo present before first non-allowed tool','evidence_refs':[]}
