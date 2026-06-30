def evaluate(trace):
    geo_bio = {'biologist_catalog_search','geographical_feature_info','green_belt_identifier','historical_biological_catalog_query','natural_landmark_locator','landmark_region_identifier','landmark_city_identifier','landmark_identifier','cultural_landmark_identifier','historical_biological_catalog_query'}
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    first_tax_idx = None
    first_geo_bio_idx = None
    for i,c in enumerate(calls):
        n = c.get('name')
        if n == 'tax_revenue_analyzer' and first_tax_idx is None:
            first_tax_idx = i
        if n in geo_bio and first_geo_bio_idx is None:
            first_geo_bio_idx = i
    if first_geo_bio_idx is None:
        return {'observed_followed': True, 'confidence':'high','reason':'no geographic or biological tools invoked','evidence_refs':[]}
    if first_tax_idx is None:
        return {'observed_followed': False, 'confidence':'medium','reason':'geo/bio tool invoked but tax_revenue_analyzer never called','evidence_refs':[{'index':first_geo_bio_idx,'name':calls[first_geo_bio_idx].get('name')}]}
    if first_tax_idx < first_geo_bio_idx:
        return {'observed_followed': True, 'confidence':'high','reason':'tax_revenue_analyzer invoked before any geographic or biological tool','evidence_refs':[{'tax_idx':first_tax_idx,'geo_bio_idx':first_geo_bio_idx}]}
    return {'observed_followed': False, 'confidence':'high','reason':'geo/bio tool invoked before tax_revenue_analyzer','evidence_refs':[{'tax_idx':first_tax_idx,'geo_bio_idx':first_geo_bio_idx}]}
