import json
import logging

from memory_as_contracts.logging_config import configure_logging, log_event


def test_mac_logging_writes_structured_json_without_protocol_stdout(tmp_path) -> None:
    log_path = tmp_path / "mac.log"
    configure_logging(path=log_path, level="INFO")

    logger = logging.getLogger("memory_as_contracts.test")
    log_event(
        logger,
        "validator.installation",
        contract_id="MAC-1",
        status="success",
    )
    for handler in logging.getLogger("memory_as_contracts").handlers:
        handler.flush()

    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert payload["event"] == "validator.installation"
    assert payload["contract_id"] == "MAC-1"
    assert payload["status"] == "success"
    assert payload["level"] == "INFO"
