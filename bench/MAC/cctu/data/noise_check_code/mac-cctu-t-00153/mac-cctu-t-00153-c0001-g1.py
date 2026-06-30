def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    valuation_tools = {'artwork_valuation_tool'}
    names = [c.get('name') for c in calls]
    # Find first valuation call
    first_val_idx = next((i for i, n in enumerate(names) if n in valuation_tools), None)
    if first_val_idx is None:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No valuation tool invoked; constraint vacuous or inapplicable', 'evidence_refs': [{'names': names}]}
    # landmark_identifier must appear before the first valuation call
    landmark_indices = [i for i, n in enumerate(names) if n == 'landmark_identifier']
    if not landmark_indices:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Valuation tool called but landmark_identifier never invoked', 'evidence_refs': [{'names': names}]}
    first_landmark = landmark_indices[0]
    if first_landmark >= first_val_idx:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'landmark_identifier at index {first_landmark} not before valuation at {first_val_idx}', 'evidence_refs': [{'names': names}]}
    # Also require landmark_identifier to be the first tool invoked overall (before any valuation tool is called)
    if first_landmark != 0:
        # Check whether anything before landmark is a valuation tool
        prior = names[:first_landmark]
        if any(n in valuation_tools for n in prior):
            return {'observed_followed': False, 'confidence': 'high', 'reason': 'Valuation tool invoked before landmark_identifier', 'evidence_refs': [{'names': names}]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'landmark_identifier precedes any valuation tool call', 'evidence_refs': [{'names': names}]}
