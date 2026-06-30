def evaluate(trace):
    import re
    traj = trace.get('trajectory') or []
    tools = ['artwork_identifier','author_geography_linker','bestselling_book_finder','cultural_heritage_locator','elevation_finder','historical_novel_finder','mountain_peak_identifier','product_price_checker','sales_tracker']
    scratch_step = None
    for i, step in enumerate(traj):
        content = (step.get('content') or '') if isinstance(step, dict) else ''
        if not content:
            continue
        lines = content.splitlines()
        numbered = [l for l in lines if re.match(r'\s*\d+[\.\)]\s+', l)]
        if len(numbered) >= 2:
            scratch_step = (i, step, content, numbered)
            break
    if scratch_step is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No numbered scratchpad list found', 'evidence_refs': []}
    i, step, content, numbered = scratch_step
    tagged = 0
    for l in numbered:
        low = l.lower()
        if any(t in low for t in tools):
            tagged += 1
    all_tagged = tagged == len(numbered)
    tcalls = step.get('tool_calls') or [] if isinstance(step, dict) else []
    no_calls_same_turn = len(tcalls) == 0
    followed = all_tagged and no_calls_same_turn
    reason = f'numbered={len(numbered)}, tagged={tagged}, tool_calls_in_turn={len(tcalls)}'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': [{'step_index': i}]}
