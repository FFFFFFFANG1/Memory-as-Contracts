def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Get first sentence
    m = re.match(r'\s*(.+?[.!?])(\s|$)', text)
    if not m:
        first = text.split('\n')[0]
    else:
        first = m.group(1)
    low = first.lower()
    keywords = ['translat']
    fidelity_terms = ['fidelity','accura','exact','precise','faithful','nuance','original','meaning','interpret','may differ','may vary','approximat']
    has_translation = any(k in low for k in keywords)
    has_fidelity = any(t in low for t in fidelity_terms)
    if has_translation and has_fidelity:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'first sentence mentions translation fidelity', 'evidence_refs': [first[:120]]}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'first sentence is not a translation-fidelity disclaimer', 'evidence_refs': [first[:120]]}
