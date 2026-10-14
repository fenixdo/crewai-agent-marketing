"""Marketing's own thinking: one agent, two crews (propose, finalize) built from the same YAML."""
from crewai import Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.project import CrewBase, agent, crew, task

from crewai_agent_marketing.fake_llm import llm
from crewai_agent_marketing.script import MarketingFakeLLM
from crewai_agent_marketing.tools.campaign import CampaignBudgetTool


@CrewBase
class ProposeCrew():
    agents: list[BaseAgent]
    tasks: list[Task]
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def marketing_lead(self) -> Agent:
        return Agent(config=self.agents_config['marketing_lead'], tools=[CampaignBudgetTool()],  # type: ignore[index]
                     llm=llm(MarketingFakeLLM), max_iter=4, verbose=True)

    @task
    def propose_task(self) -> Task:
        return Task(config=self.tasks_config['propose_task'])  # type: ignore[index]

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=True)


@CrewBase
class FinalizeCrew():
    agents: list[BaseAgent]
    tasks: list[Task]
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def marketing_lead(self) -> Agent:
        return Agent(config=self.agents_config['marketing_lead'], llm=llm(MarketingFakeLLM), max_iter=2,  # type: ignore[index]
                     verbose=True)

    @task
    def finalize_task(self) -> Task:
        return Task(config=self.tasks_config['finalize_task'])  # type: ignore[index]

    @crew
    def crew(self) -> Crew:
        return Crew(agents=self.agents, tasks=self.tasks, process=Process.sequential, verbose=True)
