def evaluate(trace):
    import re
    final = (trace.get('final_response') or '').strip()
    tool_calls = trace.get('tool_calls') or []
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to inspect.', 'evidence_refs': []}
    # Look for clarification-request signals in the final response
    clar_patterns = [r'\bclarif', r'\bcould you (please )?(clarify|specify|confirm|provide)', r'\bcan you (clarify|specify|confirm|provide)', r'\bplease (clarify|specify|confirm|provide)', r'\bwhich\b.*\?', r'\bwhat (do you mean|exactly|specifically)', r'\bbefore (i|we) (proceed|continue)', r'\bneed more (info|information|details)', r'\bmore details', r'\?']
    has_question = '?' in final
    has_clar = any(re.search(p, final, re.IGNORECASE) for p in clar_patterns)
    asks_clarification = has_question and has_clar
    # The constraint says pause before invoking *further* tools; we cannot tell when 'pause' was triggered,
    # but the final assistant turn should be the clarification request with no tools after it.
    # Check the last assistant step had no tool_calls.
    traj = trace.get('trajectory') or []
    last_assistant_has_tools = False
    for step in reversed(traj):
        if step.get('role') in (None, 'assistant'):
            tc = step.get('tool_calls') or []
            last_assistant_has_tools = bool(tc)
            break
    if asks_clarification and not last_assistant_has_tools:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'Final response requests clarification and no tool calls follow.', 'evidence_refs': []}
    if not asks_clarification:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Final response does not appear to pause and request clarification.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Tool calls appear after clarification point.', 'evidence_refs': []}
