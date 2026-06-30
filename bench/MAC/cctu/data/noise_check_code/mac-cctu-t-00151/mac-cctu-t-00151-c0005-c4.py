def evaluate(trace):
    import re
    allowed = {'landmark_locator','event_locator'}
    forbidden = {'biographical_info_retriever','population_data_retriever','age_calculator','academic_affiliation_finder_v2','explorer_achievement_finder','artwork_artist_locator'}
    traj = trace.get('trajectory') or []
    tcs = trace.get('tool_calls') or []
    if not tcs:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    # Find decomposition completion marker in assistant content
    decomp_idx = None
    patterns = re.compile(r'decompos|sub[- ]?task|breakdown|plan(ning)? complete|intake (phase )?(complete|done)|clarification (phase )?(complete|done)', re.I)
    for i, step in enumerate(traj):
        c = step.get('content') or ''
        if patterns.search(c):
            decomp_idx = i
            break
    # Collect tool calls that occurred before decomp marker (by iteration if available)
    intake_calls = []
    for tc in tcs:
        it = tc.get('iteration')
        if decomp_idx is None:
            # Without explicit marker, treat early calls (first iteration) as intake
            if it is None or it == 0 or it == (tcs[0].get('iteration')):
                intake_calls.append(tc)
        else:
            if it is None or it <= decomp_idx:
                intake_calls.append(tc)
    violations = [tc.get('name') for tc in intake_calls if tc.get('name') in forbidden]
    if violations:
        return {'observed_followed': False, 'confidence':'high','reason': f'Forbidden tools called in intake phase: {violations}','evidence_refs':[tc.get('name') for tc in intake_calls]}
    # Check intake-phase calls are within allowed set
    intake_names = [tc.get('name') for tc in intake_calls]
    out_of_scope = [n for n in intake_names if n not in allowed and n not in forbidden]
    if intake_names and all(n in allowed for n in intake_names):
        return {'observed_followed': True, 'confidence':'high','reason':'Intake-phase tools limited to landmark_locator/event_locator','evidence_refs': intake_names}
    if out_of_scope:
        return {'observed_followed': False, 'confidence':'medium','reason': f'Non-allowed tools in intake phase: {out_of_scope}','evidence_refs': intake_names}
    return {'observed_followed': None, 'confidence':'unknown','reason':'Intake phase boundary unclear','evidence_refs': intake_names}
