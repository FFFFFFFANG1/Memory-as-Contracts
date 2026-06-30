def evaluate(trace):
    allowed = {'space_mission_info_retriever','space_mission_event_finder'}
    calls = trace.get('tool_calls') or []
    used = [c.get('name') for c in calls if c.get('name')]
    forbidden_used = [n for n in used if n not in allowed]
    final = (trace.get('final_response') or '').lower()
    if forbidden_used:
        return {'observed_followed': False, 'confidence':'high','reason': f'Used disallowed tools: {forbidden_used}','evidence_refs':[]}
    if not final.strip():
        return {'observed_followed': None,'confidence':'unknown','reason':'No final response to assess milestone framing','evidence_refs':[]}
    milestone_terms = ['milestone','launch','landing','orbit','mission','rendezvous','docking','liftoff','touchdown','arrival','flyby','splashdown','crewed','uncrewed','first','achievement']
    hits = [t for t in milestone_terms if t in final]
    if hits:
        return {'observed_followed': True,'confidence':'medium','reason': f'No forbidden tools; response references milestone terms: {hits}','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'low','reason':'Response does not appear framed around mission milestones','evidence_refs':[]}
