def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no final response', 'evidence_refs': []}
    # Take the opening portion (first paragraph or first ~400 chars)
    opening = resp.split('\n\n')[0][:500].lower()
    knowledge_terms = ['pre-trained', 'pretrained', 'pre trained', 'internal knowledge', 'prior knowledge', 'training data', 'internal pre-trained', 'parametric knowledge', 'own knowledge', 'memory']
    tool_terms = ['tool output', 'tool result', 'tool-provided', 'only tool', 'tools only', 'from tools', 'via tools', 'using tools', 'tool data', 'tool-sourced', 'based on tool']
    neg_terms = ['not consult', 'did not consult', 'didn\'t consult', 'without consult', 'no internal', 'not use', 'did not use', 'didn\'t use', 'without using', 'not rel', 'did not rel', 'didn\'t rel']
    has_knowledge_ref = any(t in opening for t in knowledge_terms)
    has_tool_ref = any(t in opening for t in tool_terms)
    has_neg = any(t in opening for t in neg_terms)
    followed = (has_knowledge_ref and has_neg) and has_tool_ref
    if followed:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'Opening discloses no internal knowledge used and only tool outputs were used', 'evidence_refs': [opening[:200]]}
    return {'observed_followed': False, 'confidence': 'medium', 'reason': 'Opening lacks explicit disclosure that internal pre-trained knowledge was not consulted and only tool outputs were used', 'evidence_refs': [opening[:200]]}
