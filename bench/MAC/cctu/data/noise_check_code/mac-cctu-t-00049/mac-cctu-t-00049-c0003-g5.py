def evaluate(trace):
    import re
    response = str(trace.get('final_response') or '')
    tool_calls = trace.get('tool_calls') or []
    if not response.strip() and not tool_calls:
        return {'observed_followed': None, 'confidence': 'unknown', 'reason': 'no observable behavior', 'evidence_refs': []}
    low = response.lower()
    reasons = []
    sections = {'executive summary': 'executive summary', 'source trail': 'source trail', 'open questions': 'open questions'}
    missing = [name for name, key in sections.items() if key not in low]
    if missing:
        reasons.append('missing sections: ' + ', '.join(missing))
    dia_calls = [tc for tc in tool_calls if (tc.get('name') or '') == 'disaster_impact_analyzer']
    # Heuristic: count incidents referenced via other tool calls that imply incidents
    incident_tool_names = {'historical_event_retriever', 'geopolitical_event_finder', 'event_location_finder'}
    incident_calls = [tc for tc in tool_calls if (tc.get('name') or '') in incident_tool_names]
    # If we cannot determine the number of incidents, fall back to: at least one DIA call if any incident-like tool was used or any incident referenced in response
    incident_mentions = len(re.findall(r'incident', low))
    inferred_incidents = max(len(incident_calls), 1 if incident_mentions > 0 else 0)
    if inferred_incidents == 0 and not dia_calls:
        # No incidents discussed; the per-incident clause is vacuous
        pass
    else:
        if len(dia_calls) < max(inferred_incidents, 1):
            reasons.append('disaster_impact_analyzer called ' + str(len(dia_calls)) + ' times for ' + str(max(inferred_incidents,1)) + ' inferred incident(s)')
    if reasons:
        return {'observed_followed': False, 'confidence': 'medium', 'reason': '; '.join(reasons), 'evidence_refs': []}
    return {'observed_followed': True, 'confidence': 'medium', 'reason': 'sections present and disaster_impact_analyzer coverage met', 'evidence_refs': []}
