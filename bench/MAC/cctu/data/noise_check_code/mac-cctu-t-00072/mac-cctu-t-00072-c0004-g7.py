def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls captured', 'evidence_refs': []}
    topics = {
        'medical_school': ['educational_background_search','research_institution_finder','historical_fact_lookup'],
        'clinic_founder': ['founder_clinic_locator','clinic_remedy_finder','biographical_lookup'],
        'botanist': ['biographical_lookup','botanical_discovery_finder','historical_fact_lookup','literature_author_identifier'],
        'plant_species': ['botanical_info_retriever','botanical_discovery_finder','agricultural_data_retriever']
    }
    names = [c.get('name','') for c in calls]
    missing = []
    coverage = {}
    for topic, tools in topics.items():
        hits = [n for n in names if n in tools]
        coverage[topic] = hits
        if len(set(hits)) < 2:
            missing.append(topic)
    if missing:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': f'topics lacking >=2 distinct corroborating tool calls: {missing}', 'evidence_refs': [coverage]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'each topic has at least two distinct tool calls suggesting corroboration', 'evidence_refs': [coverage]}
