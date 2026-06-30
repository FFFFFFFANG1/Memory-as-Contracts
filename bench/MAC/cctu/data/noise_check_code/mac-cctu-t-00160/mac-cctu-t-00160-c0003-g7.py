def evaluate(trace):
    calls = trace.get('tool_calls') or []
    names = [c.get('name') for c in calls if c.get('name')]
    if not names:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    first_ok = names[0] == 'historical_figure_locator'
    last_ok = names[-1] == 'educational_institution_locator'
    eil_positions = [i for i, n in enumerate(names) if n == 'educational_institution_locator']
    eil_only_last = (not eil_positions) or eil_positions == [len(names) - 1]
    followed = first_ok and last_ok and eil_only_last
    reason = f'first={names[0]}, last={names[-1]}, eil_positions={eil_positions}'
    return {'observed_followed': bool(followed), 'confidence': 'high', 'reason': reason, 'evidence_refs': []}
