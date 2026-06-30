def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No tool calls found', 'evidence_refs': []}
    names = [c.get('name') for c in calls]
    first = names[0]
    has_supply = 'supply_chain_tracker' in names
    entry_ok = first == 'musician_instrument_finder'
    if entry_ok and has_supply:
        # ensure supply_chain_tracker happens after musician_instrument_finder and before final response (it's a tool call, so before by definition)
        mi_idx = names.index('musician_instrument_finder')
        sc_idx = names.index('supply_chain_tracker')
        if sc_idx > mi_idx:
            return {'observed_followed': True, 'confidence': 'high', 'reason': 'musician_instrument_finder used first and supply_chain_tracker traced afterward', 'evidence_refs': [{'first_tool': first, 'supply_chain_index': sc_idx}]}
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'supply_chain_tracker did not follow musician_instrument_finder', 'evidence_refs': [{'order': names}]}
    reason = []
    if not entry_ok:
        reason.append(f'entry tool was {first}, not musician_instrument_finder')
    if not has_supply:
        reason.append('supply_chain_tracker never invoked')
    return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(reason), 'evidence_refs': [{'order': names}]}
