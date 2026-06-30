def evaluate(trace):
    import re
    final = (trace.get('final_response') or '').lower()
    if not final.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    clarify_markers = ['clarify', 'clarification', 'could you specify', 'can you specify', 'please specify', 'which date', 'what date', 'which year', 'what year', 'ambiguous', 'do you mean', 'could you provide', 'please provide more', 'need more information', '?']
    relative_terms = ['recent', 'recently', 'last week', 'last month', 'last year', 'yesterday', 'today', 'tomorrow', 'this week', 'this month', 'this year', 'current', 'currently', 'now', 'latest', 'upcoming', 'soon', 'past few']
    # Look at user query in trajectory
    user_text = ''
    for step in trace.get('trajectory', []) or []:
        if isinstance(step, dict) and step.get('role') == 'user':
            user_text += ' ' + str(step.get('content') or '')
    user_text = user_text.lower()
    has_relative = any(t in user_text for t in relative_terms)
    if not has_relative:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no obvious relative/ambiguous date reference detected in user query', 'evidence_refs': []}
    asked = any(m in final for m in clarify_markers)
    if asked:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'final response appears to request clarification about ambiguous/relative date', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'relative/ambiguous date reference present but no clarification request emitted', 'evidence_refs': []}
