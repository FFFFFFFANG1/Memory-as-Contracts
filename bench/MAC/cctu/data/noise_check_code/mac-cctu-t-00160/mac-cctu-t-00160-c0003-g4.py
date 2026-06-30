def evaluate(trace):
    calls = trace.get('tool_calls') or []
    bio_tools = {'comprehensive_biographical_info_retriever','historical_figure_locator'}
    plant = 'plant_characteristics_analyzer'
    first_plant = None
    first_bio = None
    for c in calls:
        name = c.get('name')
        idx = c.get('index', 0)
        if name == plant and first_plant is None:
            first_plant = idx
        if name in bio_tools and first_bio is None:
            first_bio = idx
    if first_bio is None:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No biographical retrieval tool was called; constraint not triggered.', 'evidence_refs': []}
    if first_plant is None:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Biographical tool called without prior plant_characteristics_analyzer.', 'evidence_refs': [{'tool': 'biographical', 'index': first_bio}]}
    if first_plant < first_bio:
        return {'observed_followed': True, 'confidence': 'high', 'reason': 'plant_characteristics_analyzer was called before biographical retrieval.', 'evidence_refs': [{'plant_index': first_plant, 'bio_index': first_bio}]}
    return {'observed_followed': False, 'confidence': 'high', 'reason': 'plant_characteristics_analyzer occurred after biographical retrieval.', 'evidence_refs': [{'plant_index': first_plant, 'bio_index': first_bio}]}
