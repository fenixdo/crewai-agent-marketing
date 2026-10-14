#!/usr/bin/env python
"""Marketing chủ trì họp kế hoạch chiến dịch quý: hỏi Sale và HR qua A2A, rồi người duyệt chốt.

    intake → propose ─► ask_sale ─► ask_hr ─┬─ "ready" ───────────────────────┐
              ▲                             └─ "relay": HR hỏi lại Sale → HR ─┴─► finalize → review (HITL)
              └── "revise_round" ◄─ check_revise ◄─ "revise" ─┤ review emits approved / rejected / revise
                                                                 └─ "approved" / "rejected" ─► finish

Inputs (AMP /kickoff, trigger payload or `crewai run`): product, quarter, budget, goal.
Peers: SALE_A2A_URL / SALE_A2A_TOKEN and HR_A2A_URL / HR_A2A_TOKEN (AMP deployment URLs; their AUTH_TOKEN).
Approval: `@human_feedback(emit=[approved, rejected, revise])` → on AMP the reviewer gets three buttons (plus an
optional note) by email or on the dashboard; locally AMS_HITL=auto answers from AMS_HITL_FEEDBACK
("yêu cầu sửa: giảm ngân sách 20%||duyệt" = one answer per round). verdict() maps the answer with code.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

from crewai.flow import Flow, human_feedback, listen, or_, persist, router, start
from crewai.flow.async_feedback.types import PendingFeedbackContext
from pydantic import BaseModel

from crewai_agent_marketing.a2a_client import ask
from crewai_agent_marketing.crews.strategy_crew.strategy_crew import FinalizeCrew, ProposeCrew

MAX_REVISIONS = 2


class MeetingState(BaseModel):
    id: str = ""
    product: str = "Tori Insight"
    quarter: str = "Q1/2027"
    budget: int = 300_000_000
    goal: str = "Tăng khách hàng doanh nghiệp vừa"
    feedback: str = ""
    round: int = 0
    relayed: bool = False
    proposal: dict = {}
    forecast: dict = {}
    staffing: dict = {}
    plan: dict = {}
    transcript: list[dict] = []
    decision: str = ""
    reviewer_answer: str = ""


def verdict(answer: str | None) -> str:
    """Deterministic: 'duyệt…/approve(d)/đồng ý/ok' → approved; 'yêu cầu sửa…/sửa…/revise' → revise; else rejected."""
    t = (answer or "").strip().lower()
    if re.match(r"^(duyệt|approve|approved|đồng ý|ok\b)", t):
        return "approved"
    if re.match(r"^(yêu cầu sửa|sửa|revise)", t):
        return "revise"
    return "rejected"


class AutoReviewer:
    """Scripted reviewer for local runs: AMS_HITL_FEEDBACK holds one answer per round, split on '||'."""

    def request_feedback(self, context: PendingFeedbackContext, flow: Flow) -> str:
        answers = [a.strip() for a in os.environ.get("AMS_HITL_FEEDBACK", "duyệt").split("||")]
        return answers[min(flow.state.round, len(answers)) - 1]


OUTCOMES = ["approved", "rejected", "revise"]
# @human_feedback(emit=…) needs an llm, and on AMP the resume runs in another process that rebuilds it from its
# serialized config with LLM(model=…) — a custom BaseLLM comes back as an unknown provider and the resume dies
# (execution stays PAUSED). So: a placeholder that LLM() can build without a key or network, never called, because
# MeetingFlow._collapse_to_outcome classifies the answer with verdict().
VERDICT_LLM = "ollama/verdict-by-code"

def _provider():
    return AutoReviewer() if os.environ.get("AMS_HITL") == "auto" else None  # None → console locally, AMP's on AMP


def _peer(name: str) -> dict:
    """{NAME}_A2A_URL / _TOKEN, plus _AGENT when Sale and HR share one AMP deployment (the agent's slug)."""
    url = os.environ.get(f"{name}_A2A_URL", "")
    if not url:
        raise RuntimeError(f"thiếu {name}_A2A_URL (địa chỉ deployment {name.lower()} trên AMP)")
    return {"base_url": url, "token": os.environ.get(f"{name}_A2A_TOKEN", ""),
            "target_agent": os.environ.get(f"{name}_A2A_AGENT") or None}


def _money(v: int) -> str:
    return f"{v:,}đ".replace(",", ".")


@persist()
class MeetingFlow(Flow[MeetingState]):

    def _say(self, sender: str, to: str, text: str, data: dict | None = None) -> None:
        self.state.transcript.append({"round": self.state.round, "from": sender, "to": to, "text": text,
                                      "data": data or {}, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        print(f"[{sender} → {to}] {text}", flush=True)

    def _ask(self, peer: str, text: str, payload: dict) -> dict:
        who = {"sale": "Sale", "hr": "HR"}[peer]
        self._say("Marketing", who, text, payload)
        peer_cfg = _peer(peer.upper())
        reply_text, reply = ask(peer_cfg["base_url"], peer_cfg["token"], text, payload, peer_cfg["target_agent"])
        if reply is None:
            raise RuntimeError(f"{peer} trả lời không có JSON: {reply_text[:300]}")
        self._say(who, "Marketing", reply.get("note") or reply.get("hire_plan") or reply_text[:200], reply)
        return reply

    @start()
    def intake(self, crewai_trigger_payload: dict | None = None):
        if crewai_trigger_payload:  # AMP triggers / webhooks deliver the brief here
            for k in ("product", "quarter", "budget", "goal"):
                if k in crewai_trigger_payload:
                    setattr(self.state, k, crewai_trigger_payload[k])
        self._say("Người dùng", "Marketing", f"Lập kế hoạch chiến dịch {self.state.product} {self.state.quarter}, "
                                             f"ngân sách {_money(int(self.state.budget))}: {self.state.goal}")

    @listen(or_(intake, "revise_round"))
    def propose(self):
        self.state.round += 1
        self.state.relayed = False
        brief = {"product": self.state.product, "quarter": self.state.quarter, "budget": int(self.state.budget),
                 "goal": self.state.goal, "feedback": self.state.feedback}
        out = ProposeCrew().crew().kickoff(inputs={"brief": json.dumps(brief, ensure_ascii=False)})
        self.state.proposal = json.loads(out.raw)
        self._say("Marketing", "Cuộc họp", self.state.proposal.get("message", ""), self.state.proposal)

    @listen(propose)
    def ask_sale(self):
        p = self.state.proposal
        self.state.forecast = self._ask("sale", f"Chào Sale, chiến dịch {p.get('campaign')} dự kiến {p['target_leads']} lead "
                                                f"với ngân sách {_money(p['budget'])}. Anh/chị dự báo doanh số và số "
                                                "nhân viên bán hàng cần giúp.",
                                        {"campaign": p.get("campaign"), "target_leads": p["target_leads"], "budget": p["budget"]})

    @listen(ask_sale)
    def ask_hr(self):
        f = self.state.forecast
        self.state.staffing = self._ask("hr", f"Chào HR, Sale cần {f['sales_headcount_planned']} nhân viên bán hàng "
                                              f"(chỉ tiêu {f['quota_per_rep']} hợp đồng/người). Lập kế hoạch nhân sự giúp.",
                                        {k: f[k] for k in ("deals", "sales_headcount_needed", "sales_headcount_planned",
                                                           "quota_per_rep")})

    @router(ask_hr)
    def check_hr(self):
        return "relay" if self.state.staffing.get("open_questions") and not self.state.relayed else "ready"

    @listen("relay")
    def relay_question(self):
        """HR cannot hire enough: pass HR's question to Sale, then give HR Sale's adjusted numbers."""
        self.state.relayed = True
        q = self.state.staffing["open_questions"][0]
        self.state.forecast = self._ask("sale", f"Sale ơi, HR hỏi: {q['text']}",
                                        {"target_leads": self.state.proposal["target_leads"],
                                         "max_headcount": q["max_headcount"]})
        self.ask_hr()

    @listen(or_("ready", relay_question))
    def finalize(self):
        meeting = {"proposal": self.state.proposal, "forecast": self.state.forecast, "staffing": self.state.staffing}
        out = FinalizeCrew().crew().kickoff(inputs={"meeting": json.dumps(meeting, ensure_ascii=False)})
        self.state.plan = json.loads(out.raw)
        self._say("Marketing", "Người duyệt", self.state.plan["headline"], self.state.plan)

    @listen(finalize)
    @human_feedback(message="Duyệt kế hoạch chiến dịch? Chọn approved (duyệt), rejected (từ chối) hoặc revise "
                            "(yêu cầu sửa) — có thể ghi góp ý, ví dụ: 'yêu cầu sửa: giảm ngân sách 20%'.",
                    emit=OUTCOMES, llm=VERDICT_LLM, default_outcome="rejected",
                    provider=_provider())
    def review(self):
        p = self.state.plan
        return (f"{p['headline']}\nChi phí: marketing {_money(p['marketing_budget'])} + nhân sự "
                f"{_money(p['staffing_cost'])} = {_money(p['total_cost'])} · doanh số/chi phí {p['revenue_per_cost']}x\n"
                f"Đội bán hàng: {p['sales_team']} · {p['hiring']}\nRủi ro: {'; '.join(p['risks']) or 'không'}")

    def _collapse_to_outcome(self, feedback: str, outcomes, llm) -> str:
        """The reviewer's answer → outcome, by code (AMP's buttons send the outcome name itself)."""
        return verdict(feedback)

    def _answer(self) -> str:
        fb = self.last_human_feedback
        text = (fb.feedback if fb else "") or ""
        self.state.reviewer_answer = text or (fb.outcome if fb else "")
        self._say("Người duyệt", "Marketing", f"{fb.outcome if fb else '?'}" + (f" · {text}" if text else ""))
        return text

    @router("revise")
    def check_revise(self):
        """A revision runs another round with the reviewer's note, at most MAX_REVISIONS times."""
        self.state.feedback = self._answer()
        if self.state.round > MAX_REVISIONS:
            self._say("Marketing", "Người duyệt", f"Đã sửa {MAX_REVISIONS} lần, dừng ở đây; cần họp trực tiếp.")
            return "too_many_revisions"
        return "revise_round"

    @listen(or_("approved", "rejected", "too_many_revisions"))
    def finish(self):
        if self.last_human_feedback and self.last_human_feedback.outcome in ("approved", "rejected"):
            self._answer()
        outcome = self.last_human_feedback.outcome if self.last_human_feedback else "rejected"
        self.state.decision = "approved" if outcome == "approved" else "rejected"
        return {"decision": self.state.decision, "rounds": self.state.round, "plan": self.state.plan,
                "transcript": [{k: m[k] for k in ("round", "from", "to", "text")} for m in self.state.transcript]}


def kickoff():
    inputs = json.loads(os.environ.get("AMS_BRIEF", "{}"))
    result = MeetingFlow().kickoff(inputs=inputs)
    print(json.dumps(result, ensure_ascii=False, indent=1, default=str))


def plot():
    MeetingFlow().plot("meeting_flow")


def run_with_trigger():
    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided. Please provide JSON payload as argument.")
    result = MeetingFlow().kickoff(inputs={"crewai_trigger_payload": json.loads(sys.argv[1])})
    print(json.dumps(result, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    kickoff()
