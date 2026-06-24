from bench.MAC.scripts.run_memory_eval import merge_records_by_index


def test_merge_records_by_index_replaces_matching_rows_only() -> None:
    base = [
        {"record_type": "task_result", "index": 0, "task_uid": "t-0"},
        {"record_type": "task_error", "index": 1, "task_uid": "t-1"},
    ]
    updates = [
        {"record_type": "task_result", "index": 1, "task_uid": "t-1", "final_answer": "ok"},
    ]

    merged = merge_records_by_index(base_records=base, updates=updates, total_count=2)

    assert merged[0]["record_type"] == "task_result"
    assert merged[1]["final_answer"] == "ok"
