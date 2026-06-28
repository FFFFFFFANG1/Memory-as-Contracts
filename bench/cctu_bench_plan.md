# idea: turn long instuction short, but crud complex


## context
1. directly replace, from agentif to CCTU

2. construction file chain

	CCTU/data/input_data.jsonl + CCTU/data/check_code/
	-> bench/MAC/construct/cctu/prompt_filter.py
	-> bench/MAC/construct/cctu/cctu_adapter.py
	-> bench/MAC/construct/cctu/rule_graph.py
	-> bench/MAC/construct/cctu/graph_validation.py
	-> bench/MAC/construct/cctu/constraint_merge.py
	-> bench/MAC/construct/cctu/graph_validation.py
	-> bench/MAC/construct/cctu/task_hist_gen.py
	-> bench/MAC/construct/cctu/export_cctu_data.py
	-> bench/MAC/scripts/build_mac_data.py
	-> bench/MAC/scripts/build_mac_data.py
	-> bench/MAC/scripts/grade_cctu_answer.py


## main pipeline
for each task:
	extract all constraints
	for each c in constraints:
		construct some noisy_constraints followed by certain constraint
		validate by graph
		
	generate one task claiming c
	for each nc in noisy_constaints:
		generate one task claiming nc
	gather all task, construct task_chain, shuffle?
	# so, final task will not contain any constraint in-context
		
	for each t in task_chain:
		somehow also generate the trace


## steps
step 0: agent runtime adaptation

	tool: input original system prompt, output tool schema, add send_message_tool
	agent runtime: prompt -> reasoning -> tool call -> tool result -> response
	filter constraint from system prompt


step 1: 改写constraint
    对于每一个constraint: 
        生成conflict, 并且用scope区分
        四套prompt：global/project/phase + exception


step 3: merge constraint graphs into task-level sequence
	merge algorithm:
	for every task, prepare a constraint sequence cs = []
	for every constraint graph cg in a task:
		if cs is empty:
			cs = cg.copy()
		else:
			for every cosntraint c in cg:
				randomly insert at one index in cs, denoted as id_current
			# the next insertion can only happens between [id_current = 1, length(cg)]
			# if id_current already at the end of cs, then directly append the rest of cg to cs's end

	for each task:
		merge all per-constraint graphs into one constraint sequence
		validate chain-level contract graph

	final output:
	- `bench/MAC/mid_data/eval_step3_base_v2.json`（每 task 一条 `constraint_sequence`）
	- `bench/MAC/mid_data/eval_step3_base_v2.validated.json`（task-level chain graph + `contract_graph`）


step 4: for constraint, merge it into a task description
	for each task:
		for each constraint c in constraint sequence:
			if c is global:
				use tone like "always remeber ..."
			if c is project:
				use tone like "in this project, always ..."
			if c is phase:
				use tone like "when doing this part in the project, always ..."
			if c is exception:
				use tone like "for this time, do ..." or "<give a specific condition>, do exception"
			and generate the task chain.
	
	for llm:
		input should be current system prompt, constraint, project+phase (if scope applied)
		output should be a user prompt containing task description + constraint
			should also output response? - no
			should directly output multiple user prompt? - yes
	unify the number of task history to easy: ~10, normal: 40-60, hard: 100-150
	finally, merge preference as global to some task.

	key point: each user turn should be a realistic task the requirement should be naturally included in the task description

	key point: bench only has user turn, no assistant response, because we only focus on "user requirement".
	
	- one note: changed apply_patch constraint to “use insert_patch rather than apply_patch"


	final output:
	- `bench/MAC/mid_data/eval_step4_task_histories.json`（user-only task chain）
	- `bench/MAC/mid_data/eval_step4_system_prompt.json`（agent 级 runtime system prompt 索引）


step 4b: build final benchmark files
	`build_mac_data.py` 组装 task set + system config

	final output:
	- `bench/MAC/data/mac_easy.json`
	- `bench/MAC/data/mac_normal.json`
	- `bench/MAC/data/mac_hard.json`
	- `bench/MAC/data/mac_system_config.json`


step 5: testing
	candidate memory:
		baseline:
			no memory 
			long context
		naive:
			bm25
			embedding
			rrf
		memory system:
			mem0
			a-mem
			letta
		applied mem system:
			cc-style
			openclaw-style
		ours:
			mac
