def evaluate(trace):
    tool_calls = trace.get('tool_calls') or []
    if not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no tool calls observed; cannot verify constrained tool usage', 'evidence_refs': []}
    names = [str(c.get('name') or '') for c in tool_calls]
    bsf_indices = [i for i, n in enumerate(names) if n == 'biologist_specialization_finder']
    bsf_count = len(bsf_indices)
    if bsf_count > 3:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'biologist_specialization_finder invoked ' + str(bsf_count) + ' times, exceeds limit of 3', 'evidence_refs': [str(i) for i in bsf_indices]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'biologist_specialization_finder invoked ' + str(bsf_count) + ' times (<=3); habitat_species_associator placement unrestricted', 'evidence_refs': [str(i) for i in bsf_indices]}
