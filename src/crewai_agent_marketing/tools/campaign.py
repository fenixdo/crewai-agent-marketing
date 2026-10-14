"""campaign_budget: split the budget over channels and count the leads it buys (channels.yaml)."""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

CHANNELS = Path(__file__).resolve().parents[1] / "channels.yaml"


def campaign(budget: int) -> dict:
    rows = []
    for c in yaml.safe_load(CHANNELS.read_text())["channels"]:
        spend = budget * c["share_pct"] // 100
        rows.append({"name": c["name"], "budget": spend, "leads": spend // c["cost_per_lead"]})
    return {"budget": budget, "channels": rows, "target_leads": sum(r["leads"] for r in rows)}


class CampaignInput(BaseModel):
    budget: int = Field(..., description="Tổng ngân sách chiến dịch (đồng)")


class CampaignBudgetTool(BaseTool):
    name: str = "campaign_budget"
    description: str = "Chia ngân sách chiến dịch theo kênh và tính số lead dự kiến. Trả JSON."
    args_schema: type[BaseModel] = CampaignInput

    def _run(self, budget: int) -> str:
        return json.dumps(campaign(int(budget)), ensure_ascii=False)
