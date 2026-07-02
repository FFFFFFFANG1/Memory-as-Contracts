from __future__ import annotations

import asyncio

from bench.MAC.agent.loop.runner import ClarificationPolicy, run_agent_loop
from bench.MAC.sopbench.clarification_reply import (
    SOPClarificationContext,
    build_clarification_reply,
    is_agent_clarification_request,
)


TOOL_SCHEMAS = [
    {
        "name": "send_message",
        "description": "Submit final response.",
        "input_schema": {
            "type": "object",
            "required": ["response"],
            "properties": {"response": {"type": "string"}},
            "additionalProperties": False,
        },
    },
]


class FakeModel:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def __call__(self, *, messages, tools):
        self.calls.append({"messages": list(messages), "tools": list(tools)})
        return self.responses.pop(0)


def test_is_agent_clarification_request_detects_questions() -> None:
    assert is_agent_clarification_request("Please provide your driver's license state.")
    assert not is_agent_clarification_request("Done.")
    assert not is_agent_clarification_request("Your payment of $500 was processed successfully.")


def test_build_clarification_reply_uses_user_known_and_turns() -> None:
    reply = build_clarification_reply(
        user_prompt="Pay $500 for username john_doe.",
        past_user_turns=[
            {"kind": "carryover", "content": "Earlier I asked to pay $100 for john_doe."},
        ],
        user_known={"username": "john_doe", "pay_owed_amount_request": 500.0},
    )

    assert reply.startswith("All information I know is ")
    assert "john_doe" in reply
    assert "500" in reply


def test_sop_context_reply_for_skips_non_questions() -> None:
    context = SOPClarificationContext(
        user_prompt="Pay my loan.",
        past_user_turns=[],
        user_known={"username": "john"},
    )

    assert context.reply_for("Payment completed.") is None
    assert context.reply_for("Which state is your license in?") is not None


def test_runner_defers_clarifying_send_message_and_injects_user_reply() -> None:
    model = FakeModel(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_ask",
                        "type": "function",
                        "function": {
                            "name": "send_message",
                            "arguments": '{"response": "Please provide your driver\'s license state."}',
                        },
                    }
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_final",
                        "type": "function",
                        "function": {
                            "name": "send_message",
                            "arguments": '{"response": "Payment completed."}',
                        },
                    }
                ],
            },
        ]
    )
    context = SOPClarificationContext(
        user_prompt="Pay $500 for john_doe using license padoesshnwojord.",
        past_user_turns=[],
        user_known={"username": "john_doe", "identification": "padoesshnwojord"},
    )

    result = asyncio.run(
        run_agent_loop(
            agent="TestAgent",
            system_prompt="system",
            tools=TOOL_SCHEMAS,
            memory="",
            user_prompt=context.user_prompt,
            model_client=model,
            clarification=ClarificationPolicy(reply_for=context.reply_for, max_rounds=2),
        )
    )

    assert result.final_answer == "Payment completed."
    assert result.clarification_rounds == 1
    assert any(event["event"] == "clarification_reply" for event in result.events)
    second_call_messages = model.calls[1]["messages"]
    assert second_call_messages[-1]["role"] == "user"
    assert second_call_messages[-1]["content"].startswith("All information I know is ")
