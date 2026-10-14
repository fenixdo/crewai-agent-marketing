"""What the scripted model says as the Marketing lead (see fake_llm.py)."""
from __future__ import annotations

import re

from crewai_agent_marketing.fake_llm import ScriptedLLM, act, final, first_json, last_observation


def _money(v: int) -> str:
    return f"{v:,}đ".replace(",", ".")


class MarketingFakeLLM(ScriptedLLM):
    def respond(self, text: str) -> str:
        req = first_json(text)
        if "CHỐT KẾ HOẠCH" in text:
            return final(_plan(req), "Tổng hợp ý kiến Sale và HR thành kế hoạch trình duyệt.")
        obs = last_observation(text)
        if obs is None:  # ĐỀ XUẤT CHIẾN DỊCH: read the reviewer's note, then size the campaign with the tool
            budget = int(req.get("budget", 300_000_000))
            m = re.search(r"(?:giảm|cắt)\s*ngân sách\s*(\d+)\s*%", req.get("feedback", ""), re.I)
            if m:
                budget = budget * (100 - int(m.group(1))) // 100
            return act("campaign_budget", {"budget": budget}, "Chia ngân sách theo kênh để biết số lead.")
        return final({**obs, "campaign": f"{req.get('product', 'Tori Insight')} {req.get('quarter', '')}".strip(),
                      "objective": req.get("goal", ""),
                      "message": f"Đề xuất chiến dịch ngân sách {_money(obs['budget'])}, dự kiến {obs['target_leads']} lead."},
                     "Đã có phân bổ kênh, gửi đề xuất cho Sale.")


def _plan(d: dict) -> dict:
    p, f, s = d.get("proposal", {}), d.get("forecast", {}), d.get("staffing", {})
    spend = p.get("budget", 0) + s.get("cost", 0)
    roi = round(f.get("revenue", 0) / spend, 1) if spend else 0
    return {"headline": f"{p.get('campaign', 'Chiến dịch')}: {p.get('target_leads', 0)} lead → {f.get('deals', 0)} hợp đồng, "
                        f"doanh số {_money(f.get('revenue', 0))}",
            "marketing_budget": p.get("budget", 0), "staffing_cost": s.get("cost", 0), "total_cost": spend,
            "revenue": f.get("revenue", 0), "revenue_per_cost": roi,
            "sales_team": f"{f.get('sales_headcount_planned', 0)} người, chỉ tiêu {f.get('quota_per_rep', 0)} hợp đồng/người",
            "hiring": s.get("hire_plan", ""), "policy_version": f.get("policy_version", ""),
            "risks": f.get("risks", []),
            "next_steps": ["Chạy quảng cáo theo phân bổ kênh", "HR mở tuyển ngay tuần 1", "Sale chốt chỉ tiêu cá nhân"]}
