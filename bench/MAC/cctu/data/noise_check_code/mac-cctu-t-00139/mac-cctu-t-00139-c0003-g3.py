def evaluate(trace):
    traj = trace.get('trajectory', []) or []
    pairs_ok = 0
    pairs_bad = 0
    saw_hist = False
    for step in traj:
        calls = step.get('tool_calls') or []
        names = [ (c.get('name') or c.get('tool_name') or '') for c in calls ]
        has_hist = 'historical_event_tool' in names
        has_fin = 'financial_data_retriever' in names
        if has_hist:
            saw_hist = True
            if has_fin:
                pairs_ok += 1
            else:
                pairs_bad += 1
    if not saw_hist:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'historical_event_tool never invoked in trajectory', 'evidence_refs': []}
    if pairs_bad == 0 and pairs_ok > 0:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'{pairs_ok} historical_event_tool step(s) paired with financial_data_retriever in same iteration', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'{pairs_bad} historical_event_tool step(s) lacked parallel financial_data_retriever call', 'evidence_refs': []}
