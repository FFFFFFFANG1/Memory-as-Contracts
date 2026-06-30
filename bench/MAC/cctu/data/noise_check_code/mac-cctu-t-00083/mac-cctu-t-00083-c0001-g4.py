def evaluate(trace):
    locators = {'historical_event_locator','historical_figure_locator','indigenous_territory_locator','landmark_locator','museum_collection_finder'}
    calls = trace.get('tool_calls') or []
    locator_calls = [c for c in calls if (c.get('name') or '') in locators]
    if not locator_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'No locator tools called in trajectory.', 'evidence_refs': []}
    mcf_calls = [c for c in locator_calls if c.get('name') == 'museum_collection_finder']
    other_calls = [c for c in locator_calls if c.get('name') != 'museum_collection_finder']
    if not mcf_calls:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Alternative locator tools used without invoking museum_collection_finder first.', 'evidence_refs': [c.get('name') for c in other_calls[:3]]}
    first_mcf_idx = min((c.get('index', 0) for c in mcf_calls), default=0)
    first_other_idx = min((c.get('index', 0) for c in other_calls), default=None) if other_calls else None
    if first_other_idx is not None and first_other_idx < first_mcf_idx:
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'Another locator tool was called before museum_collection_finder.', 'evidence_refs': [c.get('name') for c in other_calls[:3]]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'museum_collection_finder was invoked before any other locator tool.', 'evidence_refs': ['museum_collection_finder']}
