from typing import Any, Dict, List

from pydantic import BaseModel, Field


class CampaignMetrics(BaseModel):
    campaign_id: str
    platform: str
    campaign_name: str
    objective: str = "lead_generation"
    status: str = "active"
    spend: float = Field(ge=0)
    budget: float = Field(ge=0)
    impressions: int = Field(ge=0)
    clicks: int = Field(ge=0)
    conversions: int = Field(ge=0)
    qualified_leads: int = Field(ge=0)
    opportunities: int = Field(ge=0)
    pipeline_value: float = Field(ge=0)
    revenue: float = Field(ge=0)
    target_cpl: float = Field(gt=0)
    frequency: float = Field(default=0, ge=0)
    previous_ctr: float = Field(default=0, ge=0)
    audience_segments: List[Dict[str, Any]] = Field(default_factory=list)
    derived_metrics: Dict[str, float] = Field(default_factory=dict)


class MarketingDataset(BaseModel):
    account_id: str
    period: str
    pipeline_target: float = Field(gt=0)
    campaigns: List[CampaignMetrics]
