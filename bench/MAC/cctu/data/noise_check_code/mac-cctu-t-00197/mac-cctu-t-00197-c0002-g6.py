def evaluate(trace):
    import re
    final = (trace.get('final_response') or '')
    traj = trace.get('trajectory') or []
    # Gather all text to look for embargo declaration
    context_text = ''
    for step in traj:
        c = step.get('content') if isinstance(step, dict) else None
        if isinstance(c, str):
            context_text += '\n' + c
    embargo_pat = re.compile(r'embargo', re.IGNORECASE)
    if not embargo_pat.search(context_text):
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No embargo declaration found in trajectory context.', 'evidence_refs': []}
    # Embargo is declared; check final response
    dollar_pat = re.compile(r'(\$\s?\d|USD\s?\d|\d[\d,]*\s?(dollars|USD))', re.IGNORECASE)
    has_dollar = bool(dollar_pat.search(final))
    has_phrase = 'price under embargo' in final.lower()
    if not has_dollar and has_phrase:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Embargo declared; response omits dollar figures and uses required phrase.', 'evidence_refs': []}
    if has_dollar:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Embargo declared but response contains dollar figures.', 'evidence_refs': []}
    if not has_phrase:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': "Embargo declared but substitute phrase 'price under embargo' missing.", 'evidence_refs': []}
    return {'observed_followed': None, 'confidence': 'low', 'reason': 'Indeterminate.', 'evidence_refs': []}
