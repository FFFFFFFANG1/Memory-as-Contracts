def evaluate(trace):
    import re
    text = (trace.get('final_response') or '').strip()
    if not text:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'empty response', 'evidence_refs': []}
    parts = re.split(r'\n\s*\n', text, maxsplit=1)
    first = parts[0].strip()
    low = first.lower()
    has_tool = 'political_event_info_retriever' in low
    disclaimer_terms = ['disclaim', 'complian', 'attest', 'sourced', 'source', 'derived', 'based']
    has_disclaimer = any(t in low for t in disclaimer_terms)
    not_internal = ('not' in low and 'internal' in low) or 'rather than internal' in low or 'no internal' in low or 'without internal' in low
    ok = has_tool and has_disclaimer
    if ok and not_internal:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'First paragraph contains compliance disclaimer referencing political_event_info_retriever and disavowing internal knowledge.', 'evidence_refs': []}
    if ok:
        return {'observed_followed': True, 'confidence': 'medium', 'reason': 'First paragraph references political_event_info_retriever as source but internal-knowledge disavowal unclear.', 'evidence_refs': []}
    return {'observed_followed': False, 'confidence': 'high' if not has_tool else 'medium', 'reason': 'Opening paragraph lacks required compliance disclaimer attesting political_event_info_retriever sourcing.', 'evidence_refs': []}
