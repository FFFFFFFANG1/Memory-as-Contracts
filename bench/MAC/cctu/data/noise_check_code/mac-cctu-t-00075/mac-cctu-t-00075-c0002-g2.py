def evaluate(trace):
    calls = trace.get('tool_calls') or []
    if not calls:
        return {'observed_followed': None, 'confidence':'unknown','reason':'no tool calls','evidence_refs':[]}
    cultural = {'cultural_geography_locator','cultural_info_retriever'}
    required = {'population_data_retriever','fishing_activity_tracker'}
    # find first iteration index for each
    def it(c):
        return c.get('iteration', c.get('index'))
    pop = [c for c in calls if c.get('name')=='population_data_retriever']
    fish = [c for c in calls if c.get('name')=='fishing_activity_tracker']
    cult = [c for c in calls if c.get('name') in cultural]
    if not pop or not fish:
        return {'observed_followed': False,'confidence':'high','reason':'missing required parallel tools','evidence_refs':[]}
    pop_it = it(pop[0]); fish_it = it(fish[0])
    parallel = pop_it is not None and pop_it == fish_it
    first_cult_it = min((it(c) for c in cult), default=None) if cult else None
    if first_cult_it is not None:
        if pop_it is None or fish_it is None or pop_it >= first_cult_it or fish_it >= first_cult_it:
            return {'observed_followed': False,'confidence':'high','reason':'cultural tool not after both required','evidence_refs':[]}
    if not parallel:
        return {'observed_followed': False,'confidence':'medium','reason':'required tools not invoked in parallel','evidence_refs':[]}
    return {'observed_followed': True,'confidence':'high','reason':'parallel required tools precede cultural lookups','evidence_refs':[]}
