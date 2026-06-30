def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {"observed_followed": None, "confidence": "unknown", "reason": "No tool calls in trajectory.", "evidence_refs": []}
    first = calls[0]
    name = first.get('name')
    if name == 'biographical_info_retriever':
        return {"observed_followed": True, "confidence": "high", "reason": "First tool call is biographical_info_retriever.", "evidence_refs": [{"index": first.get('index'), "name": name}]}
    return {"observed_followed": False, "confidence": "high", "reason": f"First tool call was {name}, not biographical_info_retriever.", "evidence_refs": [{"index": first.get('index'), "name": name}]}
