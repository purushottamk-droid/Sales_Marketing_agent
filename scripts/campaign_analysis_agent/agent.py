from google.adk.agents import LlmAgent

from .output_schema import CampaignAnalysisResult
from .prompt import CAMPAIGN_ANALYSIS_PROMPT


campaign_analysis_agent = LlmAgent(
    name="campaign_analysis_agent",
    model="gemini-2.5-flash",
    instruction=CAMPAIGN_ANALYSIS_PROMPT,
    output_schema=CampaignAnalysisResult,
    output_key="campaign_analysis_results",
    include_contents="none",
)
