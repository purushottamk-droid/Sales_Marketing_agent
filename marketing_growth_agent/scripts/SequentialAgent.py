# from google.adk.agents import SequentialAgent

# from .campaign_analysis_agent import campaign_analysis_agent
# from .data_collection_agent import DataCollectionAgent
# from .decision_action_agent import DecisionActionAgent
# from .growth_assessment_agent import growth_assessment_agent


# root_agent = SequentialAgent(
#     name="marketing_growth_pipeline",
#     sub_agents=[
#         DataCollectionAgent(name="data_collection_agent"),
#         campaign_analysis_agent,
#         growth_assessment_agent,
#         DecisionActionAgent(name="decision_action_agent"),
#     ],
# )

from google.adk.agents import SequentialAgent

from .campaign_analysis_agent import campaign_analysis_agent
from .data_collection_agent import DataCollectionAgent
from .decision_action_agent import decision_action_agent
from .growth_assessment_agent import growth_assessment_agent


root_agent = SequentialAgent(
    name="marketing_growth_pipeline",
    sub_agents=[
        DataCollectionAgent(name="data_collection_agent"),
        campaign_analysis_agent,
        growth_assessment_agent,
        decision_action_agent,
    ],
)