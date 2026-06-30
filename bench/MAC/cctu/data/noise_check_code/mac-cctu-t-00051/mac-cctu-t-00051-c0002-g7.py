def evaluate(trace):
    calls = trace.get('tool_calls', [])
    craft_tools = {'local_handicraft_identifier', 'wood_sourcing_locator'}
    prereq = {'rural_area_feature_locator', 'famous_peak_identifier'}
    names = [c.get('name') for c in calls]
    craft_idxs = [i for i, n in enumerate(names) if n in craft_tools]
    if not craft_idxs:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'No craft-related tool was invoked; precedence vacuous.', 'evidence_refs': []}
    first_craft = craft_idxs[0]
    before = set(names[:first_craft])
    missing = prereq - before
    if missing:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'Craft tool {names[first_craft]} called before required: {sorted(missing)}.', 'evidence_refs': [{'index': first_craft, 'name': names[first_craft]}]}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'Both rural_area_feature_locator and famous_peak_identifier preceded the first craft-related tool call.', 'evidence_refs': [{'index': first_craft, 'name': names[first_craft]}]}
