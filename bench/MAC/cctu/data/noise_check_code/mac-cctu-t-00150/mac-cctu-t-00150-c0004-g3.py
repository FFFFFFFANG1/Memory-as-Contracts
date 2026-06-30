def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    total = len(calls)
    first_river = None
    first_mountain = None
    for i, c in enumerate(calls):
        name = c.get('name')
        if name == 'river_width_calculator' and first_river is None:
            first_river = i
        if name == 'mountain_info_retriever' and first_mountain is None:
            first_mountain = i
    order_ok = True
    if first_mountain is not None:
        if first_river is None or first_river >= first_mountain:
            order_ok = False
    count_ok = total < 5
    followed = order_ok and count_ok
    reason = f'total_calls={total}, first_river={first_river}, first_mountain={first_mountain}, order_ok={order_ok}, count_ok={count_ok}'
    return {'observed_followed': followed, 'confidence': 'high', 'reason': reason, 'evidence_refs': []}
