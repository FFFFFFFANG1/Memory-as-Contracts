def evaluate(trace):
    calls = trace.get('tool_calls', []) or []
    names = [c.get('name') for c in calls]
    cultural = {'cuisine_explorer','culinary_ingredient_identifier','biographical_info_finder'}
    reef_idxs = [i for i,n in enumerate(names) if n=='nearby_reef_locator']
    geo_idxs = [i for i,n in enumerate(names) if n=='geographic_feature_locator']
    cult_idxs = [i for i,n in enumerate(names) if n in cultural]
    # Part 1: reef before geo
    part1 = None
    if geo_idxs:
        if not reef_idxs:
            part1 = False
            r1 = 'geographic_feature_locator called without prior nearby_reef_locator'
        elif min(reef_idxs) < min(geo_idxs):
            part1 = True
            r1 = 'nearby_reef_locator preceded geographic_feature_locator'
        else:
            part1 = False
            r1 = 'nearby_reef_locator did not precede geographic_feature_locator'
    else:
        r1 = 'no geographic_feature_locator calls; reef ordering vacuous'
    # Part 2: biodiversity tabulated before cultural lookups
    part2 = None
    r2 = ''
    if cult_idxs:
        first_cult = min(cult_idxs)
        prior = names[:first_cult]
        final = (trace.get('final_response') or '').lower()
        has_bio_tool = any(n=='nearby_reef_locator' for n in prior)
        # check final response for table-like biodiversity content (loose)
        has_table = ('|' in final and 'biodivers' in final) or ('species' in final and '|' in final)
        if has_bio_tool:
            part2 = True
            r2 = 'biodiversity-related tool called before cultural lookup'
        else:
            part2 = False
            r2 = 'cultural lookup invoked without prior biodiversity findings'
        if part2 and not has_table:
            r2 += '; tabulation of findings not clearly evidenced'
    else:
        r2 = 'no cultural lookup tools called; tabulation requirement vacuous'
    # Combine
    results = [x for x in (part1, part2) if x is not None]
    if not results:
        return {'observed_followed': None, 'confidence':'low', 'reason': r1 + ' | ' + r2, 'evidence_refs': []}
    followed = all(results)
    conf = 'high' if all(r is not None for r in (part1,part2)) else 'medium'
    return {'observed_followed': followed, 'confidence': conf, 'reason': r1 + ' | ' + r2, 'evidence_refs': []}
