def evaluate(trace):
    tcs = trace.get('tool_calls') or []
    if not tcs:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    research_or_location = {'research_location_finder','scientific_discovery_finder','desert_feature_locator','building_info_retriever','landmark_country_skyscraper_finder','nearby_college_locator','geographical_proximity_finder','elevation_finder','geographical_area_calculator'}
    def idx(c):
        return (c.get('iteration', 0), c.get('index', 0))
    ordered = sorted(tcs, key=idx)
    first_nobel = None
    first_other = None
    for i, c in enumerate(ordered):
        name = c.get('name')
        if name == 'nobel_laureate_finder' and first_nobel is None:
            first_nobel = i
        if name in research_or_location and first_other is None:
            first_other = i
    if first_other is None:
        if first_nobel is None:
            return {'observed_followed': None,'confidence':'unknown','reason':'no relevant tools used','evidence_refs':[]}
        return {'observed_followed': True,'confidence':'high','reason':'nobel_laureate_finder used; no other research/location tools called','evidence_refs':[first_nobel]}
    if first_nobel is None:
        return {'observed_followed': False,'confidence':'high','reason':'research/location tool called without prior nobel_laureate_finder','evidence_refs':[first_other]}
    if first_nobel < first_other:
        return {'observed_followed': True,'confidence':'high','reason':'nobel_laureate_finder preceded other research/location tools','evidence_refs':[first_nobel, first_other]}
    return {'observed_followed': False,'confidence':'high','reason':'other research/location tool called before nobel_laureate_finder','evidence_refs':[first_other, first_nobel]}
