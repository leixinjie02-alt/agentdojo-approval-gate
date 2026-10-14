import os
import json
from openai import OpenAI
from prompts import SYSTEM_PROMPT


# Initialize only when an assessment is requested; imports and offline tests are free.
client = None
MODEL = "openai/gpt-4o-mini"


def get_client():
    global client
    if client is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is missing")
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key,
                        timeout=30.0, max_retries=1)
    return client


# 2. Semantic Risk Assessment Function
def semantic_risk_assessment(
    user_task,
    tool_name,
    tool_parameters,
    agent_history,
    *,
    prompt=SYSTEM_PROMPT,
    tool_description=""
):

    # Prepare tool call information
    tool_context = {
        "user_task": user_task,
        "tool_name": tool_name,
        "tool_parameters": tool_parameters,
        "agent_history": agent_history,
        "tool_description": tool_description
    }

    try:
        # 3. Call the LLM
        response = get_client().chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": prompt
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        tool_context,
                        ensure_ascii=False
                    )
                }
            ],
            temperature=0,
            max_tokens=300
        )

        # 4. Parse the LLM response
        content = response.choices[0].message.content

        result = json.loads(content)

        if not isinstance(result, dict):
            return "escalate"
        decision = result.get("decision")
        reason = result.get("reason", "")

        # 5. Validate the decision
        valid_decisions = [
            "auto_approve",
            "auto_deny",
            "escalate"
        ]

        if decision not in valid_decisions:
            print("Invalid LLM decision.")
            return "escalate"

        return decision

    except Exception as e:
        print("LLM assessment failed:", type(e).__name__)
        print("Fallback decision: escalate")
        return "escalate"


# 6. Test
if __name__ == "__main__":

    result = semantic_risk_assessment(
        user_task="Help me prepare the deployment configuration",
        tool_name="modify_file",
        tool_parameters={
            "path": "production_config.yaml",
            "changes": "Update the database connection settings"
        },
        agent_history=[]
    )

    print("\nFinal Policy Decision:", result)
