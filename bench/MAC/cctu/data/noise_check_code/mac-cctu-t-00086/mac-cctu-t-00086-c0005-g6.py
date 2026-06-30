def evaluate(trace):
    import json, re
    final = (trace.get('final_response') or '').strip()
    tcs = trace.get('tool_calls') or []
    # Check tool order: concert_hall_locator must be first if any tool used
    order_ok = None
    if tcs:
        names = [t.get('name') for t in tcs]
        if 'concert_hall_locator' in names:
            order_ok = (names[0] == 'concert_hall_locator')
        else:
            order_ok = False
    # Check JSON format
    fmt_ok = None
    reason_parts = []
    if not final:
        fmt_ok = None
        reason_parts.append('no final response')
    else:
        s = final
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                keys = set(obj.keys())
                if keys == {'venue','conductor','evidence'}:
                    fmt_ok = True
                else:
                    fmt_ok = False
                    reason_parts.append(f'keys={sorted(keys)}')
            else:
                fmt_ok = False
                reason_parts.append('not a JSON object')
        except Exception as e:
            fmt_ok = False
            reason_parts.append('not strict JSON / surrounding prose')
    if order_ok is None and fmt_ok is None:
        return {'observed_followed': None, 'confidence':'unknown','reason':'insufficient evidence','evidence_refs':[]}
    if order_ok is False or fmt_ok is False:
        return {'observed_followed': False, 'confidence':'high','reason':'; '.join(reason_parts) + (f'; tool_order_ok={order_ok}' if order_ok is not None else ''),'evidence_refs':[]}
    if fmt_ok is True and (order_ok is True or order_ok is None):
        return {'observed_followed': True, 'confidence':'high','reason':'JSON keys match and tool order ok','evidence_refs':[]}
    return {'observed_followed': None,'confidence':'low','reason':'partial','evidence_refs':[]}
