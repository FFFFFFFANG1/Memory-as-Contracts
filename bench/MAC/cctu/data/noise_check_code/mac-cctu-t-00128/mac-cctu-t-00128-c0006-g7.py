def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls observed','evidence_refs':[]}
    names = [c.get('name') for c in calls]
    non_allowed = [n for n in names if n and n != 'unified_media_info_retriever']
    total = len(names)
    if non_allowed:
        return {'observed_followed': False,'confidence':'high','reason': f'used disallowed tools: {non_allowed}','evidence_refs': names}
    if total > 3:
        return {'observed_followed': False,'confidence':'high','reason': f'tool calls {total} exceed cap of 3','evidence_refs': names}
    return {'observed_followed': True,'confidence':'high','reason': f'only unified_media_info_retriever used, total {total} <= 3','evidence_refs': names}
