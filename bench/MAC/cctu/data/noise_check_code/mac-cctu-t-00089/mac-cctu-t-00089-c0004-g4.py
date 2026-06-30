def evaluate(trace):
    preferred = {'attraction_locator','historical_landmark_locator','cultural_geography_locator'}
    forbidden = {'hospital_survival_rate_analyzer','medical_research_center_locator','nearby_supplier_locator','supplier_hospital_locator'}
    calls = trace.get('tool_calls') or []
    names = [c.get('name') for c in calls]
    used_forbidden = [n for n in names if n in forbidden]
    used_preferred = [n for n in names if n in preferred]
    resp = (trace.get('final_response') or '').strip()
    if not resp and not calls:
        return {'observed_followed': None,'confidence':'unknown','reason':'no evidence','evidence_refs':[]}
    # single paragraph check: no blank line separators
    paragraphs = [p for p in resp.split('\n\n') if p.strip()]
    single_para = len(paragraphs) <= 1 and resp != ''
    tool_ok = (len(used_forbidden) == 0) and (len(calls) == 0 or len(used_preferred) > 0)
    followed = tool_ok and single_para
    reason = f'forbidden_used={used_forbidden}, preferred_used={used_preferred}, paragraphs={len(paragraphs)}'
    return {'observed_followed': bool(followed),'confidence':'high' if resp else 'medium','reason': reason,'evidence_refs': []}
