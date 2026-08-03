from google.adk.agents import LlmAgent

from .output_schema import GrowthAssessmentResult
from .prompt import GROWTH_ASSESSMENT_PROMPT


growth_assessment_agent = LlmAgent(
    name="growth_assessment_agent",
    model="gemini-2.5-flash",
    instruction=GROWTH_ASSESSMENT_PROMPT,
    output_schema=GrowthAssessmentResult,
    output_key="growth_assessment_result",
    include_contents="none",
)
