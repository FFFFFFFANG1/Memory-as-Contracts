def evaluate(trace):
    import re
    text = trace.get('final_response') or ''
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response to evaluate.', 'evidence_refs': []}
    contractions = ["n't", "'re", "'ve", "'ll", "'d", "'m", "'s ", "won't", "can't", "don't", "isn't", "aren't", "wasn't", "weren't", "i'm", "you're", "they're", "we're", "it's", "that's", "there's", "let's", "who's"]
    low = text.lower()
    found_contractions = [c for c in contractions if c in low]
    colloquial_terms = ['gonna','wanna','gotta','kinda','sorta','yeah','yep','nope','ok','okay','cool','awesome','stuff','things like that','a lot of','lots of','tons of','guys','folks','hey','hi there','basically','pretty much','sort of','kind of']
    found_colloquial = [w for w in colloquial_terms if re.search(r'\b' + re.escape(w) + r'\b', low)]
    issues = []
    if found_contractions:
        issues.append('Contractions detected: ' + ', '.join(found_contractions[:5]))
    if found_colloquial:
        issues.append('Colloquialisms detected: ' + ', '.join(found_colloquial[:5]))
    if issues:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(issues), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'No contractions or obvious colloquialisms detected; register appears formal.', 'evidence_refs': []}
