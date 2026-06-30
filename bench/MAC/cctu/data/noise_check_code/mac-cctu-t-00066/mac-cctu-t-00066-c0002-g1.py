def evaluate(trace):
    allowed = {'educational_figure_identifier','educational_history_search'}
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls found','evidence_refs':[]}
    # Identify educator-identification phase as the leading block of calls,
    # which should only contain the two allowed tools before any other lookup.
    leading_other = None
    leading_allowed_seen = False
    for i, c in enumerate(calls):
        name = c.get('name')
        if name in allowed:
            leading_allowed_seen = True
            continue
        else:
            leading_other = (i, name)
            break
    if leading_other is None:
        return {'observed_followed': True, 'confidence':'medium','reason':'all tool calls were the two educator tools','evidence_refs':[]}
    idx, other_name = leading_other
    if not leading_allowed_seen:
        return {'observed_followed': False, 'confidence':'high','reason': f'first tool call was {other_name}, not an educator identification tool','evidence_refs':[{'index': idx, 'name': other_name}]}
    # Check no allowed call appears mixed after another lookup begins — i.e., the educator phase preceded other lookups cleanly.
    # If after the first other call, we still see allowed tools later, the phase was not cleanly bounded; treat as followed only if leading block was pure.
    return {'observed_followed': True, 'confidence':'medium','reason': f'educator tools used before switching to {other_name} at index {idx}','evidence_refs':[{'index': idx, 'name': other_name}]}
