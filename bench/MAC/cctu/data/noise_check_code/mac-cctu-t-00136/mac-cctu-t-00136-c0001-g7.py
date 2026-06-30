def evaluate(trace):
    tcs = trace.get('tool_calls') or []
    if not tcs:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls observed', 'evidence_refs': []}
    pam_idx = None
    hist_idx = None
    refs = []
    for i, c in enumerate(tcs):
        name = (c.get('name') or '').lower()
        order = c.get('index', i)
        if name == 'personal_asset_manager' and pam_idx is None:
            pam_idx = order
            refs.append({'tool': name, 'index': order})
        if name.startswith('historical_') and hist_idx is None:
            hist_idx = order
            refs.append({'tool': name, 'index': order})
    if hist_idx is None and pam_idx is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no relevant tools invoked', 'evidence_refs': []}
    if hist_idx is not None and pam_idx is None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'historical tool invoked without prior personal_asset_manager call', 'evidence_refs': refs}
    if pam_idx is not None and hist_idx is None:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'personal_asset_manager invoked; no historical tool used', 'evidence_refs': refs}
    if pam_idx < hist_idx:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'personal_asset_manager invoked before historical tool', 'evidence_refs': refs}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'historical tool invoked before personal_asset_manager', 'evidence_refs': refs}
