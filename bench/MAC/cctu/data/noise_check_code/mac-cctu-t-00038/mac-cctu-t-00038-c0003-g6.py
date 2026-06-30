def evaluate(trace):
    import re
    tcs = trace.get('tool_calls') or []
    military_like = {'military_event_search','historical_event_data_retriever','historical_event_finder','historical_event_identifier','historical_event_info_retriever','historical_event_locator','historical_event_search'}
    used = []
    for tc in tcs:
        n = (tc.get('name') or '').lower()
        if n in military_like:
            used.append(n)
    distinct = set(used)
    final = (trace.get('final_response') or '')
    traj = trace.get('trajectory') or []
    log_text = final + '\n'
    for step in traj:
        c = step.get('content') or ''
        if c:
            log_text += str(c) + '\n'
        for tc in (step.get('tool_calls') or []):
            r = tc.get('result')
            if r is not None:
                log_text += str(r) + '\n'
    casualty_kw = re.search(r'casualt|killed|deaths|dead|wounded|fatalities|losses', log_text, re.I)
    if not casualty_kw:
        return {'observed_followed': None, 'confidence':'unknown', 'reason':'No casualty figures discussed in trajectory; constraint may not apply or evidence missing.', 'evidence_refs':[]}
    if len(distinct) < 2:
        return {'observed_followed': False, 'confidence':'high', 'reason': f'Casualty figures mentioned but only {len(distinct)} distinct military-event tool(s) used: {sorted(distinct)}.', 'evidence_refs':[{'tools_used': sorted(distinct)}]}
    reconcile_kw = re.search(r'reconcil|cross[- ]?verif|cross[- ]?check|compare|consistent|discrepan|both sources|sources agree|sources differ|matches|confirm', log_text, re.I)
    if not reconcile_kw:
        return {'observed_followed': False, 'confidence':'medium', 'reason':'Two+ military-event tools called but no explicit reconciliation language found in observation log.', 'evidence_refs':[{'tools_used': sorted(distinct)}]}
    return {'observed_followed': True, 'confidence':'medium', 'reason': f'Casualty figures discussed, {len(distinct)} distinct military-event tools called, and reconciliation language detected.', 'evidence_refs':[{'tools_used': sorted(distinct)}]}
