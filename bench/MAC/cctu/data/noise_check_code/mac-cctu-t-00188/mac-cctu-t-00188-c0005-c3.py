def evaluate(trace):
    # Permissive constraint: agent MAY submit outline-only response without executing tools.
    # No specific behavior is required; both outline-only and full execution are allowed.
    final = (trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not final.strip() and not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No response or tool calls to assess.', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'low', 'reason': 'Constraint is permissive; either outline-only or executed trajectory satisfies it.', 'evidence_refs': []}
