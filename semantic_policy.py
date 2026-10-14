import json
import logging
import os
from openai import OpenAI
from prompts import SYSTEM_PROMPT


# Initialize only when an assessment is requested; imports and offline tests are free.
client = None
MODEL = "openai/gpt-4o-mini"

# Token usage of the most recent assessment, read by SemanticPolicy for cost accounting.
LAST_USAGE = {}
log = logging.getLogger(__name__)


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

    global LAST_USAGE
    LAST_USAGE = {}
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
            max_tokens=300,
            # Force a JSON object so a formatting slip does not silently become "escalate".
            response_format={"type": "json_object"},
        )

        usage = getattr(response, "usage", None)
        if usage is not None:
            LAST_USAGE = {"prompt_tokens": usage.prompt_tokens,
                          "completion_tokens": usage.completion_tokens}

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
            log.warning("Invalid LLM decision: %r", decision)
            return "escalate"

        return decision

    except Exception as e:
        log.warning("LLM assessment failed (%s); fallback decision: escalate", type(e).__name__)
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