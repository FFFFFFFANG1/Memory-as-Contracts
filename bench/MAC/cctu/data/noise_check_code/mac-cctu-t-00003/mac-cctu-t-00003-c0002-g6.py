def evaluate(trace):
    import re
    text = (trace.get('final_response') or '')
    if not text.strip():
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No final response', 'evidence_refs': []}
    low = text.lower()
    partisan_terms = ['democrat', 'republican', 'gop', 'partisan', 'party control', 'd-r', 'r-d']
    legislature_terms = ['legislature', 'state house', 'state senate', 'state assembly', 'general assembly', 'statehouse']
    federal_terms = ['federal', 'congress', 'senate', 'house of representatives', 'presiden']
    has_partisan = any(t in low for t in partisan_terms)
    has_legislature = any(t in low for t in legislature_terms)
    has_federal = any(t in low for t in federal_terms)
    # Look for multiple states enumerated
    state_names = ['alabama','alaska','arizona','arkansas','california','colorado','connecticut','delaware','florida','georgia','hawaii','idaho','illinois','indiana','iowa','kansas','kentucky','louisiana','maine','maryland','massachusetts','michigan','minnesota','mississippi','missouri','montana','nebraska','nevada','new hampshire','new jersey','new mexico','new york','north carolina','north dakota','ohio','oklahoma','oregon','pennsylvania','rhode island','south carolina','south dakota','tennessee','texas','utah','vermont','virginia','washington','west virginia','wisconsin','wyoming']
    state_count = sum(1 for s in state_names if s in low)
    followed = has_partisan and has_legislature and has_federal and state_count >= 3
    reason = f'partisan={has_partisan}, legislature={has_legislature}, federal={has_federal}, states_mentioned={state_count}'
    return {'observed_followed': bool(followed), 'confidence': 'medium', 'reason': reason, 'evidence_refs': []}
