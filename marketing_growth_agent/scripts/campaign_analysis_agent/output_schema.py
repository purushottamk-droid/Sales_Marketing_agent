from typing import List, Literal

from pydantic import BaseModel, Field


class SegmentInsight(BaseModel):
    segment: str
    evidence: str


class CampaignAnalysis(BaseModel):
    campaign_id: str
    campaign_name: str
    platform: str
    campaign_health: Literal["healthy", "watch", "at_risk", "critical"]
    efficiency_score: int = Field(ge=0, le=100)
    growth_potential: Literal["low", "medium", "high"]
    high_intent_segments: List[SegmentInsight] = Field(default_factory=list)
    performance_issues: List[str] = Field(default_factory=list)
    recommended_action: str
    analysis_summary: str


class CampaignAnalysisResult(BaseModel):
    campaigns: List[CampaignAnalysis]
