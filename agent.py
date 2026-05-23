import os
from dotenv import load_dotenv
from langchain_openai import AzureChatOpenAI
from langchain.agents import create_agent

from tools import get_idle_vms, resize_vm

load_dotenv(override=True)

llm = AzureChatOpenAI(
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
    api_version="2024-10-21",
    temperature=0
)

tools = [get_idle_vms, resize_vm]

system_prompt = """
You are an Azure VM cost optimization assistant.

You have two tools:
1. get_idle_vms - finds idle Azure VMs using CPU metrics.
2. resize_vm - previews or resizes a VM.

Rules:
- Always use get_idle_vms when the user asks to find idle VMs.
- For resizing, first call resize_vm with approval='no' to show a preview.
- Never call resize_vm with approval='yes' unless the user clearly says they approve the resize.
- If user asks to resize vm-runbook, use resource group rg-infra-lab unless user gives another resource group.
- Keep answers short and practical.
"""

agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=system_prompt
)


def ask_agent(user_input: str) -> str:
    result = agent.invoke({
        "messages": [
            {"role": "user", "content": user_input}
        ]
    })

    final_message = result["messages"][-1]
    return final_message.content


if __name__ == "__main__":
    print("Azure VM Cost Optimization Agent")
    print("Type 'exit' to quit.")

    while True:
        user_input = input("\nYou: ")

        if user_input.lower().strip() in ["exit", "quit"]:
            print("Exiting.")
            break

        try:
            response = ask_agent(user_input)
            print("\nAgent:", response)
        except Exception as e:
            print("\nError:", str(e))
