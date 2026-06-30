def evaluate(trace):
    import re
    tool_calls = trace.get('tool_calls', []) or []
    final = (trace.get('final_response') or '')
    used_hist = any((tc.get('name') or '') == 'historical_event_retriever' for tc in tool_calls)
    if not used_hist:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'historical_event_retriever was not called to cross-reference magnitudes', 'evidence_refs': []}
    text = final.lower()
    has_compare_terms = any(t in text for t in ['discrepan', 'differ', 'compar', 'match', 'consistent', 'agree'])
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', final) if p.strip()]
    comparative_para = None
    for p in paragraphs:
        pl = p.lower()
        if any(t in pl for t in ['discrepan','differ','compar','consistent','agree']) and ('magnitud' in pl or 'source' in pl or 'historical' in pl):
            comparative_para = p
            break
    if comparative_para is None and has_compare_terms:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'Comparison vocabulary present but no clear comparative paragraph identified', 'evidence_refs': []}
    if comparative_para is None:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'No comparative paragraph summarizing discrepancies between the two sources found in final response', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'historical_event_retriever was used and a comparative paragraph discussing discrepancies is present', 'evidence_refs': [comparative_para[:160]]}
