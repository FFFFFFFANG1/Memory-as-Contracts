def evaluate(trace):
    import re
    historical_tools = {'historical_event_data_retriever','historical_event_date_tool','historical_event_tool','historical_fact_retriever'}
    calls = trace.get('tool_calls') or []
    hist_calls = [c for c in calls if (c.get('name') or '') in historical_tools]
    if not hist_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No historical tool calls found to evaluate cross-verification.', 'evidence_refs': []}
    def norm_args(a):
        if isinstance(a, dict):
            vals = [str(v).strip().lower() for v in a.values() if v is not None]
            return ' | '.join(sorted(vals))
        return str(a).strip().lower()
    groups = {}
    for c in hist_calls:
        key = norm_args(c.get('arguments'))
        groups.setdefault(key, []).append(c)
    unpaired = []
    paired = []
    for key, cs in groups.items():
        tools_used = {c.get('name') for c in cs}
        if len(tools_used) >= 2:
            paired.append((key, list(tools_used)))
        else:
            unpaired.append((key, list(tools_used)))
    if unpaired:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{len(unpaired)} retrieval query(ies) were not cross-verified by a second historical tool: {unpaired[:3]}', 'evidence_refs': [str(unpaired[:3])]}
    traj = trace.get('trajectory') or []
    log_text = ''
    for step in traj:
        c = step.get('content') or ''
        log_text += '\n' + str(c)
    verbatim_hits = 0
    checked = 0
    for c in hist_calls:
        res = c.get('result')
        if res is None:
            continue
        checked += 1
        snippet = str(res).strip()
        if not snippet:
            continue
        probe = snippet[:60]
        if probe and probe in log_text:
            verbatim_hits += 1
    if checked > 0 and verbatim_hits < checked:
        return {'observed_followed': False, 'confidence': 'low', 'reason': f'Only {verbatim_hits}/{checked} raw historical tool responses appear stored verbatim in the working log.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': f'All {len(paired)} retrieval queries cross-verified by a second historical tool with raw responses present in log.', 'evidence_refs': []}
