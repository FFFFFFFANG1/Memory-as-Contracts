def evaluate(trace):
    import re
    final=trace.get('final_response','') or ''
    calls=trace.get('tool_calls',[]) or []
    tool_names=[c.get('name','') for c in calls if c.get('name')]
    distinct=set(tool_names)
    categories={
        'election_result_fetcher':'election',
        'historical_event_search':'historical',
        'historical_figure_identifier':'historical',
        'maritime_incident_finder':'maritime',
        'political_event_retriever':'political',
        'political_leadership_tracker':'political',
    }
    cats=set(categories.get(n) for n in distinct if n in categories)
    has_cross = len(calls)>=2 and len(cats)>=2
    text=final.lower()
    has_footnote = bool(re.search(r'footnote', text)) or bool(re.search(r'\n\s*\[\^?\d+\]', final)) or bool(re.search(r'\n\s*\d+\.\s', final))
    has_ids = bool(re.search(r'(payload|id|identifier)', text))
    if not calls:
        return {'observed_followed': False, 'confidence':'high', 'reason':'no tool calls to cross-verify', 'evidence_refs': []}
    if has_cross and has_footnote and has_ids:
        return {'observed_followed': True, 'confidence':'medium', 'reason':'cross-category tool calls and footnote with identifiers found', 'evidence_refs': sorted(list(cats))}
    if not has_cross:
        return {'observed_followed': False, 'confidence':'medium', 'reason':'fewer than two tool categories used', 'evidence_refs': sorted(list(cats))}
    return {'observed_followed': False, 'confidence':'low', 'reason':'footnote block citing payload identifiers not detected', 'evidence_refs': []}
