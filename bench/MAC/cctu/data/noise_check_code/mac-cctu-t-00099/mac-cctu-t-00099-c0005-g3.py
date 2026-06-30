def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    hist = [c for c in calls if c.get('name')=='historical_event_locator']
    if not hist:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no historical_event_locator calls','evidence_refs':[]}
    others = [c for c in calls if c.get('name') and c.get('name')!='historical_event_locator']
    distinct_others = {c.get('name') for c in others}
    # Need at least 2 independent validations per historical_event_locator result
    needed = 2 * len(hist)
    if len(others) >= needed and len(distinct_others) >= 2:
        return {'observed_followed': True, 'confidence':'medium','reason':f'{len(hist)} historical calls, {len(others)} validating calls across {len(distinct_others)} distinct tools','evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium','reason':f'{len(hist)} historical calls but only {len(others)} other calls across {len(distinct_others)} distinct tools (need >={needed} across >=2 tools)','evidence_refs':[]}
