def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    folk_calls = [tc for tc in tool_calls if (tc.get('name') or '') == 'cultural_heritage_folk_tale_finder']
    if not response.strip() and not tool_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no observable behavior', 'evidence_refs': []}
    if not folk_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'cultural_heritage_folk_tale_finder was not invoked to cross-reference claims', 'evidence_refs': []}
    text = response.lower()
    citation_terms = ['folk', 'folklore', 'tale', 'heritage', 'cultural_heritage_folk_tale_finder', 'record', 'source', 'cited', 'citation', 'origin']
    has_citation = any(term in text for term in citation_terms)
    if not has_citation:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'response does not cite an originating folklore record', 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'folk tale finder invoked and folklore citation present in response', 'evidence_refs': [f'folk_calls={len(folk_calls)}']}
