from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ActionRecord(BaseModel):
    type: Literal[
        "budget_change",
        "campaign_alert",
        "creative_refresh",
        "growth_review",
        "growth_experiment",
    ]
    status: Literal["PROPOSED", "SKIPPED", "ERROR"]
    campaign_id: Optional[str] = None
    reason: str
    approval_required: bool = True
    payload: Dict[str, Any] = Field(default_factory=dict)


class DecisionActionResult(BaseModel):
    actions: List[ActionRecord] = Field(default_factory=list)
