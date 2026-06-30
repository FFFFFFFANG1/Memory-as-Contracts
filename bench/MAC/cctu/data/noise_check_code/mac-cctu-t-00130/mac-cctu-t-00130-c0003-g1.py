def evaluate(trace):
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls; constraint requires at least 4 distinct retrieval calls', 'evidence_refs': []}
    names = [str(c.get('name') or '') for c in tool_calls if c.get('name')]
    distinct = set(n for n in names if n)
    target = 'product_and_appliance_specification_retriever'
    target_count = sum(1 for n in names if n == target)
    reasons = []
    if len(distinct) < 4:
        reasons.append('only ' + str(len(distinct)) + ' distinct tool(s) called; need at least 4')
    if target_count > 5:
        reasons.append(target + ' called ' + str(target_count) + ' times, exceeds max of 5')
    if reasons:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'at least 4 distinct tools called and product_and_appliance_specification_retriever within 5-call cap', 'evidence_refs': []}
