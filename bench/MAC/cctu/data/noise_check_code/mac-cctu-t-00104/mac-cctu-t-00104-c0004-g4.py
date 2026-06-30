def evaluate(trace):
    calls = trace.get('tool_calls', []) or []
    total = len(calls)
    sc = [c for c in calls if (c.get('name') or '') == 'species_counter']
    if total > 7:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Exceeded 7 total tool calls: {total}', 'evidence_refs': []}
    if len(sc) < 1:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'species_counter not invoked', 'evidence_refs': []}
    # Try to infer affected regions from species_counter arguments
    regions = set()
    for c in sc:
        args = c.get('arguments') or {}
        if isinstance(args, dict):
            for k, v in args.items():
                if 'region' in str(k).lower() and isinstance(v, str):
                    regions.add(v.strip().lower())
    # Look for region mentions elsewhere (final response / trajectory) - heuristic unknown
    text = (trace.get('final_response') or '')
    for step in (trace.get('trajectory') or []):
        text += '\n' + str(step.get('content') or '')
    # Without ground truth list of affected regions we cannot fully verify per-region coverage
    return {'observed_followed': None, 'confidence': 'low', 'reason': f'species_counter called {len(sc)}x, total={total}; cannot enumerate affected regions to confirm per-region coverage', 'evidence_refs': []}
