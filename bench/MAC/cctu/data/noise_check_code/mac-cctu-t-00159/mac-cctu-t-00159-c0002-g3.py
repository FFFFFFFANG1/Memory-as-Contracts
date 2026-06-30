def evaluate(trace):
    traj = trace.get('trajectory') or []
    tcs = trace.get('tool_calls') or []
    # Rule 1: one tool call per assistant turn
    over = []
    for i, step in enumerate(traj):
        calls = step.get('tool_calls') or []
        if len(calls) > 1:
            over.append((i, len(calls)))
    # Rule 2: any valley logging (natural_feature_locator) must occur before any mine lookup (subterranean_mine_locator)
    mine_indices = [c.get('index', k) for k, c in enumerate(tcs) if c.get('name') == 'subterranean_mine_locator']
    valley_indices = [c.get('index', k) for k, c in enumerate(tcs) if c.get('name') == 'natural_feature_locator']
    order_ok = True
    reason_parts = []
    if mine_indices and valley_indices:
        if min(mine_indices) < max(valley_indices):
            order_ok = False
            reason_parts.append('mine lookup occurred before all valley logs')
    elif mine_indices and not valley_indices:
        order_ok = False
        reason_parts.append('mine lookup without any preceding valley log')
    if over:
        reason_parts.append(f'turns with >1 tool call: {over}')
    if not tcs:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls observed', 'evidence_refs': []}
    followed = (not over) and order_ok
    return {'observed_followed': followed, 'confidence': 'high' if followed else 'medium', 'reason': '; '.join(reason_parts) or 'one call per turn and valleys precede mines', 'evidence_refs': []}
