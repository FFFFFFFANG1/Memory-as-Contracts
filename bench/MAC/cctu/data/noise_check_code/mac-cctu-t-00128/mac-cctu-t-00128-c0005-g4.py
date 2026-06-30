def evaluate(trace):
    # Constraint is permissive: exploratory drafts MAY use bullets with rough depths
    # and NEED NOT include numeric baseline differences. It grants latitude rather
    # than imposing a requirement, so absent contradictory evidence it is followed.
    final = (trace.get('final_response') or '')
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to assess.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'low', 'reason': 'Permissive allowance; no violation possible from output content alone.', 'evidence_refs': []}
