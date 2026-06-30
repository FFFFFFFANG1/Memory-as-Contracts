def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty final response', 'evidence_refs': []}
    first_line = resp.splitlines()[0].strip()
    low = first_line.lower()
    # Must mention not using internal/pre-trained knowledge
    neg = any(n in low for n in [' no ', 'not ', 'without', "didn't", 'did not', 'none of'])
    neg = neg or low.startswith('no ')
    knowledge_terms = ['pre-trained', 'pretrained', 'pre trained', 'internal knowledge', 'internal pre-trained', 'prior knowledge', 'training data', 'parametric knowledge', 'internal pretrained']
    has_knowledge = any(t in low for t in knowledge_terms)
    attest_terms = ['attest', 'certify', 'confirm', 'compliance', 'declare', 'affirm', 'state']
    has_attest = any(t in low for t in attest_terms) or 'knowledge' in low
    if neg and has_knowledge and has_attest:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'first line is a compliance statement about no internal pre-trained knowledge', 'evidence_refs': [{'first_line': first_line}]}
    if has_knowledge and neg:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'first line negates use of pre-trained knowledge', 'evidence_refs': [{'first_line': first_line}]}
    return {'observed_followed': False, 'confidence': 'high' if first_line else 'medium', 'reason': 'first line is not a compliance statement attesting no internal pre-trained knowledge was used', 'evidence_refs': [{'first_line': first_line}]}
