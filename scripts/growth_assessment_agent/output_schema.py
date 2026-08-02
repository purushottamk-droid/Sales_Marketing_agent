from typing import List, Literal

from pydantic import BaseModel, Field


class BudgetRecommendation(BaseModel):
    campaign_id: str
    direction: Literal["increase", "decrease", "hold", "pause"]
    percent: int = Field(ge=0, le=100)
    amount: float = Field(default=0, ge=0)
    destination_channel: str = ""
    reason: str


class ExperimentRecommendation(BaseModel):
    name: str
    hypothesis: str
    primary_metric: str
    campaign_ids: List[str]


class PerformanceGroup(BaseModel):
    category: Literal[
        "Top Performers", "Underperformers", "High Cost / Low Quality"
    ]
    campaign_ids: List[str] = Field(default_factory=list)
    evidence: str


class ChannelEfficiency(BaseModel):
    channel: str
    cpl: float = Field(ge=0)
    cpo: float = Field(ge=0)
    ctr: float = Field(ge=0)
    cpc: float = Field(ge=0)
    lead_to_opportunity_rate: float = Field(ge=0)
    quality_assessment: str


class PerformanceShift(BaseModel):
    channel_or_campaign: str
    direction: Literal["improving", "declining", "stable", "insufficient_data"]
    evidence: str


class BuyerProfile(BaseModel):
    rank: int = Field(ge=1, le=3)
    name: str
    job_titles: List[str] = Field(default_factory=list)
    industries: List[str] = Field(default_factory=list)
    company_attributes: List[str] = Field(default_factory=list)
    strongest_channels: List[str] = Field(default_factory=list)
    evidence: str


class ChannelForecast(BaseModel):
    rank: int = Field(ge=1)
    channel: str
    open_leads: int = Field(ge=0)
    historical_lead_to_opportunity_rate: float = Field(ge=0)
    projected_opportunities: float = Field(ge=0)
    projected_pipeline_value: float = Field(ge=0)
    assumed_stage_win_rate: float = Field(ge=0, le=1)
    spend: float = Field(ge=0)
    forecasted_roi: float
    assumptions: str


class ChannelAllocation(BaseModel):
    channel: str
    current_spend: float = Field(ge=0)
    recommended_spend: float = Field(ge=0)
    change_amount: float
    change_percent: float
    rationale: str


class IcpCriterion(BaseModel):
    priority: int = Field(ge=1)
    attribute: str
    target_value: str
    evidence: str


class CampaignGrowthAssessment(BaseModel):
    campaign_id: str
    performance_category: Literal[
        "Top Performers", "Underperformers", "High Cost / Low Quality"
    ]
    projected_qualified_leads: float = Field(ge=0)
    projected_opportunities: float = Field(ge=0)
    projected_pipeline_value: float = Field(ge=0)
    assumed_win_rate: float = Field(ge=0, le=1)
    forecasted_roi: float
    budget_direction: Literal["increase", "decrease", "hold", "pause"]
    budget_change_percent: int = Field(ge=0, le=100)
    growth_outlook: Literal["Low", "Medium", "High"]
    recommendation: str
    evidence: str
    forecast_available: bool
    data_gap: str = ""


class GrowthAssessmentResult(BaseModel):
    forecast_period: str
    forecasted_qualified_leads: int = Field(ge=0)
    forecasted_opportunities: int = Field(ge=0)
    forecasted_pipeline: float = Field(ge=0)
    target_attainment: int = Field(ge=0, le=200)
    overall_growth_risk: Literal["Low", "Medium", "High"]
    budget_recommendations: List[BudgetRecommendation] = Field(default_factory=list)
    priority_segments: List[str] = Field(default_factory=list)
    experiment_recommendations: List[ExperimentRecommendation] = Field(default_factory=list)
    performance_groups: List[PerformanceGroup] = Field(default_factory=list)
    channel_efficiency: List[ChannelEfficiency] = Field(default_factory=list)
    month_over_month_shifts: List[PerformanceShift] = Field(default_factory=list)
    high_intent_buyer_profiles: List[BuyerProfile] = Field(default_factory=list)
    channel_forecasts: List[ChannelForecast] = Field(default_factory=list)
    channel_budget_allocation: List[ChannelAllocation] = Field(default_factory=list)
    ideal_customer_profile_summary: str = ""
    target_account_criteria: List[IcpCriterion] = Field(default_factory=list)
    campaign_assessments: List[CampaignGrowthAssessment] = Field(default_factory=list)
    data_gaps: List[str] = Field(default_factory=list)
    recommended_next_steps: List[str] = Field(default_factory=list)
    needs_manager_attention: bool
    executive_summary: str
