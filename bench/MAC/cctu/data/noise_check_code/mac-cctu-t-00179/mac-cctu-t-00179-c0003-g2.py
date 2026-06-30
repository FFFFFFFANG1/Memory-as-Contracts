import re

TOOLS = ['academic_paper_finder','architectural_designer_finder','biodiversity_database','biographical_info_retriever','capital_city_lookup','city_area_calculator','innovation_country_identifier','organization_locator','research_location_identifier','satellite_info_retriever','sports_venue_info']

def evaluate(trace):
    trace = trace or {}
    final = str(trace.get('final_response') or '')
    trajectory = trace.get('trajectory') or []
    tool_calls = trace.get('tool_calls') or []
    failures = []
    evidence = []

    # 1. Each listed tool at most once
    counts = {}
    order = []
    for c in tool_calls:
        n = str(c.get('name') or '')
        counts[n] = counts.get(n, 0) + 1
        order.append(n)
    for t in TOOLS:
        if counts.get(t, 0) > 1:
            failures.append(f'{t} called {counts[t]} times (max 1)')

    # 2. At least 6 interaction rounds
    rounds = len(trajectory)
    evidence.append({'interaction_rounds': rounds})
    if rounds < 6:
        failures.append(f'interaction rounds {rounds} below minimum 6')

    # 3. biodiversity_database before satellite_info_retriever
    if 'satellite_info_retriever' in order:
        if 'biodiversity_database' not in order:
            failures.append('biodiversity_database not called before satellite_info_retriever')
        else:
            bi = order.index('biodiversity_database')
            si = order.index('satellite_info_retriever')
            if bi >= si:
                failures.append('biodiversity_database must precede satellite_info_retriever')

    # 4. Response format checks
    if not final:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'missing final response', 'evidence_refs': evidence}

    if 'Species Count: ' not in final:
        failures.append("missing 'Species Count: '")
    else:
        m = re.search(r'Species Count:\s*([\d,]+(?:\.\d+)?)', final)
        if not m:
            failures.append("'Species Count: ' not followed by a number")

    if 'Satellite Weight (kg): ' not in final:
        failures.append("missing 'Satellite Weight (kg): '")
    else:
        m = re.search(r'Satellite Weight \(kg\):\s*([\d,]+(?:\.\d+)?)', final)
        if not m:
            failures.append("'Satellite Weight (kg): ' not followed by a number")

    # Separator line '---- Comparison ----' on its own line
    sep_match = re.search(r'(?m)^\s*----\s*Comparison\s*----\s*$', final)
    if not sep_match:
        failures.append("missing separator line '---- Comparison ----'")
    else:
        # The separator must come before the final comparison statement
        after = final[sep_match.end():].strip()
        if not after:
            failures.append("no final comparison statement after separator")
        else:
            # Species Count and Satellite Weight should appear before separator
            before = final[:sep_match.start()]
            if 'Species Count: ' not in before:
                failures.append("'Species Count: ' should appear before separator")
            if 'Satellite Weight (kg): ' not in before:
                failures.append("'Satellite Weight (kg): ' should appear before separator")

    if not final.rstrip().endswith('.'):
        failures.append('final response must end with a period')

    if failures:
        return {'observed_followed': False, 'confidence': 'high', 'reason': '; '.join(failures[:10]), 'evidence_refs': evidence}
    return {'observed_followed': True, 'confidence': 'high', 'reason': 'all constraint checks passed', 'evidence_refs': evidence}
