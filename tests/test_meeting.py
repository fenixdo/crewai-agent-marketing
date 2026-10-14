"""Offline tests of the meeting flow: Sale and HR are stubbed (no network), the reviewer is scripted."""
import pytest

import crewai_agent_marketing.main as m
from crewai_agent_marketing.tools.campaign import campaign


def test_verdict_is_parsed_by_code():
    assert m.verdict("Duyệt, triển khai đi") == "approved"
    assert m.verdict("yêu cầu sửa: giảm ngân sách 20%") == "revise"
    assert m.verdict("từ chối: quá đắt") == "rejected"
    assert m.verdict("") == "rejected"


def test_campaign_buys_leads_per_channel():
    c = campaign(300_000_000)
    assert c["target_leads"] == sum(r["leads"] for r in c["channels"]) > 0


def fake_peer(url, token, text, payload, target_agent=None):
    """Sale needs 7 people unless capped; HR can staff 6, so the first answer comes back with a question."""
    if "sale" in url:
        reps = payload.get("max_headcount") or 7
        return "ok", {"deals": 60, "revenue": 1_944_000_000, "sales_headcount_needed": 7, "sales_headcount_planned": reps,
                      "quota_per_rep": -(-60 // reps), "policy_version": "v1", "risks": [], "note": f"cần {reps} người"}
    need = payload["sales_headcount_planned"]
    q = [{"to": "sale", "max_headcount": 6, "text": "chỉ tuyển được 3"}] if need > 6 else []
    return "ok", {"hire_plan": f"tuyển {min(need - 3, 3)}", "cost": 99, "open_questions": q}


@pytest.fixture(autouse=True)
def peers(monkeypatch):
    monkeypatch.setattr(m, "ask", fake_peer)
    for k in ("SALE", "HR"):
        monkeypatch.setenv(f"{k}_A2A_URL", f"http://{k.lower()}")
        monkeypatch.setenv(f"{k}_A2A_TOKEN", "t")


def meeting(monkeypatch, answers: str) -> tuple[dict, m.MeetingFlow]:
    monkeypatch.setenv("AMS_HITL_FEEDBACK", answers)
    flow = m.MeetingFlow()
    return flow.kickoff(inputs={}), flow


def test_hr_question_is_relayed_to_sale_then_approved(monkeypatch):
    out, flow = meeting(monkeypatch, "duyệt")
    senders = [(t["from"], t["to"]) for t in out["transcript"]]
    assert senders.count(("Marketing", "Sale")) == 2 and senders.count(("Marketing", "HR")) == 2
    assert flow.state.forecast["sales_headcount_planned"] == 6
    assert out["decision"] == "approved" and out["rounds"] == 1


def test_revise_runs_another_round_with_smaller_budget(monkeypatch):
    out, flow = meeting(monkeypatch, "yêu cầu sửa: giảm ngân sách 20%||duyệt")
    assert out["decision"] == "approved" and out["rounds"] == 2
    assert flow.state.proposal["budget"] == 240_000_000


def test_reject(monkeypatch):
    out, _ = meeting(monkeypatch, "từ chối: chi phí cao")
    assert out["decision"] == "rejected" and out["rounds"] == 1


def test_revisions_are_capped(monkeypatch):
    out, _ = meeting(monkeypatch, "yêu cầu sửa: giảm ngân sách 10%")
    assert out["decision"] == "rejected" and out["rounds"] == m.MAX_REVISIONS + 1


@pytest.mark.parametrize("answer,outcome", [("approved", "approved"), ("revise", "revise"), ("rejected", "rejected"),
                                            ("yêu cầu sửa: giảm ngân sách 20%", "revise"), ("Duyệt", "approved")])
def test_collapse_maps_buttons_and_free_text(answer, outcome):
    assert m.MeetingFlow()._collapse_to_outcome(answer, m.OUTCOMES, None) == outcome


@pytest.mark.parametrize("answer,decision", [("approved", "approved"), ("rejected", "rejected")])
def test_pause_then_resume_in_a_new_flow_like_amp(monkeypatch, answer, decision):
    """AMP pauses at review, persists, and resumes later in another process from the stored context (the llm is
    rebuilt from its serialized config). A custom BaseLLM there broke the resume and left the execution PAUSED."""
    from crewai.flow.async_feedback.types import HumanFeedbackPending

    def pause(self, context, flow):
        raise HumanFeedbackPending(context=context)

    monkeypatch.setattr(m.AutoReviewer, "request_feedback", pause)
    flow = m.MeetingFlow()
    assert isinstance(flow.kickoff(inputs={}), HumanFeedbackPending)
    out = m.MeetingFlow.from_pending(flow.state.id).resume(answer)
    assert out["decision"] == decision and out["rounds"] == 1
