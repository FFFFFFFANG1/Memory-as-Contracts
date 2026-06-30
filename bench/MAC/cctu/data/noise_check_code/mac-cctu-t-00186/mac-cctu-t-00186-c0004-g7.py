def evaluate(trace):
    import re
    calls = trace.get('tool_calls', []) or []
    if not calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no tool calls recorded', 'evidence_refs': []}
    geo_tools = {'desert_feature_locator','elevation_finder','geographical_area_calculator','geographical_proximity_finder','landmark_country_skyscraper_finder','nearby_college_locator','research_location_finder'}
    dfl_indices = [i for i, c in enumerate(calls) if c.get('name') == 'desert_feature_locator']
    other_geo_indices = [i for i, c in enumerate(calls) if c.get('name') in geo_tools and c.get('name') != 'desert_feature_locator']
    if len(dfl_indices) < 2:
        return {'observed_followed': False, 'confidence': 'high', 'reason': f'desert_feature_locator called {len(dfl_indices)} time(s), expected 2', 'evidence_refs': [{'tool_calls': dfl_indices}]}
    first_two = dfl_indices[:2]
    if other_geo_indices and min(other_geo_indices) < max(first_two):
        return {'observed_followed': False, 'confidence': 'high', 'reason': 'another geographical tool ran before two desert_feature_locator calls completed', 'evidence_refs': [{'first_other_geo_index': min(other_geo_indices), 'dfl_indices': first_two}]}
    subjects = []
    for i in first_two:
        args = calls[i].get('arguments') or {}
        if isinstance(args, dict):
            vals = [str(v).lower() for v in args.values() if isinstance(v,(str,int,float))]
            subjects.append(' | '.join(vals))
        else:
            subjects.append(str(args).lower())
    if subjects[0].strip() == subjects[1].strip() and subjects[0].strip():
        return {'observed_followed': False, 'confidence': 'medium', 'reason': 'the two desert_feature_locator calls used identical subjects', 'evidence_refs': [{'subjects': subjects}]}
    water_hint = re.compile(r'sea|ocean|gulf|bay|lake|river|strait|channel|sound|water')
    has_water = any(water_hint.search(s) for s in subjects)
    if not has_water:
        return {'observed_followed': None, 'confidence': 'low', 'reason': 'could not confirm a water-body subject among the two calls', 'evidence_refs': [{'subjects': subjects}]}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'two desert_feature_locator calls with distinct subjects (one water-body-like) ran before other geographical tools', 'evidence_refs': [{'subjects': subjects, 'dfl_indices': first_two}]}
