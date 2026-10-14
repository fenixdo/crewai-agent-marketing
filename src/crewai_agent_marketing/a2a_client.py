"""Talk to another agent over A2A (JSON-RPC `message/send`, protocol 0.3) — generated from ams/template/a2a_client.py.

    ask(base_url, token, text, payload) → (reply_text, reply_json_or_None)

base_url is the peer's root (AMP deployment URL or a local server). Its public agent card
(/.well-known/agent-card.json) gives the JSON-RPC endpoint; calls carry `Authorization: Bearer <token>`.
On AMP the token is the peer DEPLOYMENT's bearer token (Status tab / API `token`); AMP's gateway checks it
before the agent runs. Locally (scripts/a2a_local.py) it is the peer's AUTH_TOKEN. The payload travels as a ```json block in the text so any
agent reads it, plus a DataPart for clients that use structured parts.
"""
from __future__ import annotations

import json
import re
import uuid

import httpx

TIMEOUT = httpx.Timeout(180.0, connect=15.0)


class A2AError(RuntimeError):
    pass


def _endpoint(base_url: str, client: httpx.Client) -> str:
    """The JSON-RPC URL from the peer's public agent card. AMP's card advertises its in-cluster address
    (http://127.0.0.1:80/a2a), so a card pointing at localhost while the base is remote means <base>/a2a."""
    base = base_url.rstrip("/")
    card = client.get(base + "/.well-known/agent-card.json")
    if card.status_code != 200:
        raise A2AError(f"không đọc được agent card ({card.status_code}) tại {base_url}")
    url = card.json().get("url") or ""
    host = httpx.URL(url).host if url else ""
    if not url or (host in ("127.0.0.1", "localhost") and httpx.URL(base).host not in ("127.0.0.1", "localhost")):
        return base + "/a2a"
    return url


def _texts(obj) -> list[str]:
    """Every text part in a Task or Message result (artifacts first, then the status message)."""
    out = []
    for art in obj.get("artifacts") or []:
        out += [p.get("text", "") for p in art.get("parts", []) if p.get("kind") == "text"]
    msg = (obj.get("status") or {}).get("message") or (obj if obj.get("kind") == "message" else None)
    if msg:
        out += [p.get("text", "") for p in msg.get("parts", []) if p.get("kind") == "text"]
    return [t for t in out if t]


def ask(base_url: str, token: str, text: str, payload: dict | None = None,
        target_agent: str | None = None) -> tuple[str, dict | None]:
    """target_agent: on an AMP deployment that serves several A2A agents, the slug of the one to talk to
    (sent as message metadata, as AMP documents); without it AMP answers with the crew's first agent."""
    body = text + ("\n\n```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```" if payload else "")
    parts = [{"kind": "text", "text": body}] + ([{"kind": "data", "data": payload}] if payload else [])
    message = {"kind": "message", "role": "user", "messageId": str(uuid.uuid4()), "parts": parts}
    if target_agent:
        message["metadata"] = {"target_agent": target_agent}
    req = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": "message/send",
           "params": {"message": message, "configuration": {"blocking": True}}}
    with httpx.Client(timeout=TIMEOUT, headers={"Authorization": f"Bearer {token}"}) as c:
        r = c.post(_endpoint(base_url, c), json=req)
    if r.status_code != 200:
        raise A2AError(f"A2A HTTP {r.status_code}: {r.text[:300]}")
    data = r.json()
    if "error" in data:
        raise A2AError(f"A2A lỗi: {data['error']}")
    result = data.get("result") or {}
    state = (result.get("status") or {}).get("state")
    if state and state not in ("completed", "input-required"):
        raise A2AError(f"A2A task kết thúc ở trạng thái {state}")
    reply = "\n".join(_texts(result)).strip()
    m = re.search(r"\{.*\}", reply, re.S)
    try:
        return reply, json.loads(m.group(0)) if m else None
    except ValueError:
        return reply, None
