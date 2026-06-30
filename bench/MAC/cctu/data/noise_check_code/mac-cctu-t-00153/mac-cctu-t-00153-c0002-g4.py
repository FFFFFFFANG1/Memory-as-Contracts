def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls', 'evidence_refs': []}
    names = [(i, c.get('name')) for i, c in enumerate(calls)]
    disambig = {'city_feature_identifier','city_reputation_identifier','artist_location_finder','company_locator','historical_residence_finder'}
    valuation = {'artwork_valuation_tool','financial_data_retriever'}
    val_idxs = [i for i,n in names if n in valuation]
    if not val_idxs:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no downstream valuation tool invoked; constraint vacuous', 'evidence_refs': []}
    disambig_idxs = [i for i,n in names if n in disambig]
    if not disambig_idxs:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'no city disambiguation step detected', 'evidence_refs': []}
    landmark_idxs = [i for i,n in names if n == 'landmark_identifier']
    first_val = min(val_idxs)
    first_disambig = min(disambig_idxs)
    valid_landmarks = [i for i in landmark_idxs if first_disambig < i < first_val]
    if not valid_landmarks:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'no landmark_identifier call between city disambiguation and valuation tool', 'evidence_refs': [str(first_disambig), str(first_val)]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'landmark_identifier invoked after disambiguation and before valuation', 'evidence_refs': [str(i) for i in valid_landmarks]}
