def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls found', 'evidence_refs': []}
    allowed = {'historical_research_locator', 'historical_fact_retriever'}
    calculators = {'advanced_calculator', 'area_calculator', 'enhanced_arithmetic_calculator'}
    first = calls[0].get('name')
    if first not in allowed:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'initial tool was {first}, not a historical source tool', 'evidence_refs': [{'index': calls[0].get('index'), 'name': first}]}
    # Walk through initial source gathering phase: contiguous prefix of allowed tools
    saw_historical = False
    for c in calls:
        name = c.get('name')
        if name in allowed:
            saw_historical = True
            continue
        # first non-allowed call: check if calculator appeared before any allowed (impossible since first was allowed)
        if name in calculators and not saw_historical:
            return {'observed_followed': False, 'confidence': 'high', 'reason': f'calculator {name} invoked during initial source gathering', 'evidence_refs': [{'index': c.get('index'), 'name': name}]}
        break
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'initial source gathering used only historical_research_locator/historical_fact_retriever before any calculator', 'evidence_refs': [{'index': calls[0].get('index'), 'name': first}]}
