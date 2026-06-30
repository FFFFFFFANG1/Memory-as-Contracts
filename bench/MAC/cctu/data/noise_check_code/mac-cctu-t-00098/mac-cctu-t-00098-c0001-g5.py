def evaluate(trace):
    tcs = trace.get('tool_calls') or []
    traj = trace.get('trajectory') or []
    n_calls = len(tcs)
    n_turns = len(traj)
    names = [tc.get('name') for tc in tcs]
    over_calls = n_calls > 4
    over_turns = n_turns > 5
    used_pef = any(n == 'political_event_finder' for n in names)
    if over_calls or over_turns:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'turns={n_turns}, tool_calls={n_calls}; exceeds limits (5 turns, 4 calls)', 'evidence_refs': []}
    if n_calls == 0:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No tool calls; cannot assess prioritization of political_event_finder', 'evidence_refs': []}
    if not used_pef:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'political_event_finder not used among {names}; not prioritized', 'evidence_refs': []}
    first = names[0]
    pef_share = sum(1 for n in names if n == 'political_event_finder') / max(1, n_calls)
    prioritized = (first == 'political_event_finder') or (pef_share >= 0.5)
    if prioritized:
        return {'observed_followed': True, 'confidence': 'high', 'reason': f'Within limits (turns={n_turns}, calls={n_calls}); political_event_finder prioritized (first={first}, share={pef_share:.2f})', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': f'political_event_finder used but not prioritized (first={first}, share={pef_share:.2f})', 'evidence_refs': []}
