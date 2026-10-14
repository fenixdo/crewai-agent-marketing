"""Scripted LLM for demos and tests — generated from ams/template/fake_llm.py (edit there, then run
`python ams/scripts/sync_template.py`).

The fake answers the way a real model does in CrewAI's ReAct loop, so the whole framework runs for real: the agent
reads the task, calls its tool ("Action: … / Action Input: {…}"), reads the Observation, then writes
"Final Answer: <JSON>"; output_pydantic, guardrails and flows all see ordinary model output. No network, no key.

    llm()   → the real model when MODEL is set (e.g. MODEL=anthropic/claude-sonnet-5-5 + its API key),
              otherwise this repo's ScriptedLLM subclass (see script.py).
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from crewai import LLM
from crewai.llms.base_llm import BaseLLM

OBS = re.compile(r"Observation:\s*(\{.*?\})\s*(?:\n|$)", re.S)
JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.S)


def text_of(messages: Any) -> str:
    if isinstance(messages, str):
        return messages
    return "\n".join(str(m.get("content", "")) for m in messages if isinstance(m, dict))


def last_observation(text: str) -> dict | None:
    """The JSON a tool returned in this conversation (the last one), if the agent already called it."""
    found = OBS.findall(text)
    return json.loads(found[-1]) if found else None


def first_json(text: str) -> dict:
    """The JSON payload a request carries (in a ```json block, as the Marketing flow and the A2A messages send it)."""
    m = JSON_BLOCK.search(text)
    return json.loads(m.group(1)) if m else {}


def act(tool: str, args: dict, thought: str) -> str:
    return f"Thought: {thought}\nAction: {tool}\nAction Input: {json.dumps(args, ensure_ascii=False)}"


def final(payload: dict, thought: str) -> str:
    return f"Thought: {thought}\nFinal Answer: {json.dumps(payload, ensure_ascii=False)}"


class ScriptedLLM(BaseLLM):
    """Subclasses implement respond(text) → the model's reply. Deterministic; FAKE_LLM_DELAY adds a pause per call."""

    def respond(self, text: str) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    def call(self, messages, tools=None, callbacks=None, available_functions=None, from_task=None, from_agent=None,
             response_model=None):
        time.sleep(float(os.environ.get("FAKE_LLM_DELAY", "0.2")))
        reply = self.respond(text_of(messages))
        if response_model is not None and "Final Answer:" in reply:  # structured output asked for directly
            return reply.split("Final Answer:", 1)[1].strip()
        return reply

    def supports_function_calling(self) -> bool:  # ReAct text loop; crewai's converter calls this unguarded
        return False

    def supports_stop_words(self) -> bool:
        return False


def llm(fake_cls: type[ScriptedLLM], max_tokens: int = 2000):
    model = os.environ.get("MODEL", "").strip()
    if model:
        return LLM(model=model, max_tokens=max_tokens)
    return fake_cls(model="fake/scripted")
