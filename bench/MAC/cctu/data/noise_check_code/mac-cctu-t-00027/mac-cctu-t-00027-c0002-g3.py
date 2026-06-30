def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    names = [c.get('name') for c in calls]
    first = names[0]
    if first != 'diplomatic_recognition_tracker':
        return {'observed_followed': False, 'confidence':'high','reason':f'first tool was {first}, not diplomatic_recognition_tracker','evidence_refs':[{'index':0,'name':first}]}
    drt_idx = 0
    follow_up = None
    for i in range(drt_idx+1, len(names)):
        if names[i] == 'historical_event_finder':
            follow_up = i
            break
    if follow_up is None:
        return {'observed_followed': False, 'confidence':'high','reason':'no historical_event_finder follow-up after diplomatic_recognition_tracker','evidence_refs':[{'sequence':names}]}
    return {'observed_followed': True, 'confidence':'high','reason':'diplomatic_recognition_tracker first, followed by historical_event_finder','evidence_refs':[{'first':0,'follow_up':follow_up}]}
