def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    traj = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    text_parts = [final]
    for step in traj:
        c = step.get('content') if isinstance(step, dict) else None
        if c: text_parts.append(str(c))
    full_text = '\n'.join(text_parts).lower()
    if not tool_calls and not full_text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No trajectory content or tool calls to inspect.', 'evidence_refs': []}
    justification_terms = ['because','justif','reason','selected','chosen','chose','rationale','over alternative','instead of','preferred','suitable']
    has_justifications = any(t in full_text for t in justification_terms)
    flagged_sub = ('subscription_price_checker_merged' in full_text) and any(k in full_text for k in ['out-of-scope','out of scope','irrelevant','not relevant','not applicable','excluded'])
    flagged_smart = ('smartphone_specification_retriever' in full_text) and any(k in full_text for k in ['out-of-scope','out of scope','irrelevant','not relevant','not applicable','excluded'])
    per_call_ok = True
    if tool_calls:
        # Heuristic: count justification keyword occurrences vs number of calls
        count_just = sum(full_text.count(t) for t in ['because','justif','rationale','selected','chosen'])
        per_call_ok = count_just >= len(tool_calls)
    followed = has_justifications and per_call_ok and flagged_sub and flagged_smart
    reason = f'justifications={has_justifications}, per_call_ok={per_call_ok}, flagged_subscription={flagged_sub}, flagged_smartphone={flagged_smart}, num_tool_calls={len(tool_calls)}'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
