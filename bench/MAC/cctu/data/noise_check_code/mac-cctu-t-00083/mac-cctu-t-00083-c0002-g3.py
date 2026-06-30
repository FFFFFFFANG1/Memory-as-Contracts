def evaluate(trace):
    calls = trace.get('tool_calls', []) or []
    museum_idxs = [i for i,c in enumerate(calls) if c.get('name')=='museum_collection_finder']
    symbol_idxs = [i for i,c in enumerate(calls) if c.get('name')=='cultural_symbol_identifier']
    total_museum = len(museum_idxs)
    if symbol_idxs:
        first_symbol = symbol_idxs[0]
        museum_before = sum(1 for i in museum_idxs if i < first_symbol)
        if museum_before >= 2:
            return {'observed_followed': True, 'confidence':'high', 'reason': f'museum_collection_finder called {museum_before} times before first cultural_symbol_identifier call', 'evidence_refs':[]}
        else:
            return {'observed_followed': False, 'confidence':'high', 'reason': f'only {museum_before} museum_collection_finder calls before cultural_symbol_identifier (need >=2)', 'evidence_refs':[]}
    # No symbol identifier tool used; check if final response makes cultural symbol claims
    final = (trace.get('final_response') or '').lower()
    claim_terms = ['cultural symbol','symbolize','symbolic meaning','represents the','symbol of']
    has_claim = any(t in final for t in claim_terms)
    if not has_claim:
        return {'observed_followed': None, 'confidence':'low', 'reason':'no cultural symbol claim detected; constraint not clearly triggered', 'evidence_refs':[]}
    if total_museum >= 2:
        return {'observed_followed': True, 'confidence':'medium', 'reason': f'{total_museum} museum_collection_finder calls before final cultural symbol claim', 'evidence_refs':[]}
    return {'observed_followed': False, 'confidence':'medium', 'reason': f'cultural symbol claim made with only {total_museum} museum_collection_finder calls', 'evidence_refs':[]}
