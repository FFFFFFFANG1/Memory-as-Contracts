def evaluate(trace):
    import re
    final=(trace.get('final_response') or '')
    calls=trace.get('tool_calls') or []
    used_tt=any((c.get('name')=='time_tracker') for c in calls)
    words=len(final.split())
    has_latency=bool(re.search(r'latency', final, re.IGNORECASE))
    under=words<=80 and words>0
    ok=used_tt and has_latency and under
    reason=f"time_tracker_used={used_tt}, latency_line={has_latency}, words={words}"
    return {"observed_followed": bool(ok), "confidence": "high" if (used_tt or final) else "low", "reason": reason, "evidence_refs": []}
