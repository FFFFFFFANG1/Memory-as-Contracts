def evaluate(trace):
    import re
    resp = (trace.get('final_response') or '').strip()
    if not resp:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no final response','evidence_refs':[]}
    tools = ['election_result_finder','eurovision_winner_info','historical_event_locator','international_agreement_finder','lunar_eclipse_counter','space_mission_tracker','sports_event_winner_finder']
    called = [c.get('name') for c in (trace.get('tool_calls') or []) if c.get('name')]
    # Split response into sentences/lines
    parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+|\n+', resp) if p.strip()]
    if not parts:
        return {'observed_followed': None,'confidence':'unknown','reason':'no content','evidence_refs':[]}
    # Find provenance mentions naming a tool
    mentions = [p for p in parts if any(t in p.lower() for t in tools) or re.search(r'\b(source|provenance|via|using|from|produced by|according to)\b', p, re.I)]
    if not called:
        # No tool calls; if response makes factual claims without provenance, fail; hard to judge
        if mentions:
            return {'observed_followed': True,'confidence':'low','reason':'provenance mentions present though no tool calls','evidence_refs':[]}
        return {'observed_followed': None,'confidence':'unknown','reason':'no tool calls and no provenance language','evidence_refs':[]}
    # Heuristic: at least one provenance sentence naming a used tool
    named_used = any(any(t in p.lower() for t in called) for p in parts)
    if named_used:
        return {'observed_followed': True,'confidence':'medium','reason':'response references the tool(s) used','evidence_refs':[]}
    if mentions:
        return {'observed_followed': False,'confidence':'low','reason':'provenance language present but does not name the actual tool used','evidence_refs':[]}
    return {'observed_followed': False,'confidence':'medium','reason':'no provenance note naming a tool found alongside factual answer','evidence_refs':[]}
