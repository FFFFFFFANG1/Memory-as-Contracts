def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    cultural = {'book_info_retriever','hit_song_finder'}
    geo_species = {'cultural_origin_locator','district_feature_locator','flora_geography_locator','individual_location_finder','species_counter','tree_species_analyzer'}
    first_geo_idx = None
    cultural_before = set()
    evidence = []
    for i, c in enumerate(calls):
        name = c.get('name')
        if name in geo_species and first_geo_idx is None:
            first_geo_idx = i
            evidence.append({'index':i,'tool':name,'role':'first_geo_species'})
            break
        if name in cultural:
            cultural_before.add(name)
            evidence.append({'index':i,'tool':name,'role':'cultural'})
    if first_geo_idx is None:
        # no geography/species tool used; precondition for ordering not triggered
        if cultural_before:
            return {'observed_followed': True,'confidence':'medium','reason':'cultural tools used; no geo/species tools invoked','evidence_refs':evidence}
        return {'observed_followed': None,'confidence':'low','reason':'no geo/species tool invoked and no cultural calls observed','evidence_refs':evidence}
    if cultural == cultural_before:
        return {'observed_followed': True,'confidence':'high','reason':'both cultural tools called before any geo/species tool','evidence_refs':evidence}
    missing = list(cultural - cultural_before)
    return {'observed_followed': False,'confidence':'high','reason': f'geo/species tool {calls[first_geo_idx].get("name")} called before cultural tools: missing {missing}','evidence_refs':evidence}
