import _paths  # noqa: F401  (sets up imports; see project_paths.py)
import os
import csv
import json
import time
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from prompts import (
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_V2,
    SYSTEM_PROMPT_V3
)
from test_dataset import TEST_CASES


# 1. OpenRouter Configuration

API_KEY = os.getenv("OPENROUTER_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "OPENROUTER_API_KEY is not configured."
    )

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=API_KEY,
    timeout=30.0,
    max_retries=1
)

MODEL = "openai/gpt-4o-mini"
RESULT_FILE = _paths.RESULTS_DIR / ("semantic_results_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".csv")


# 2. Prompt Versions

PROMPTS = {
    "V1": SYSTEM_PROMPT,
    "V2": SYSTEM_PROMPT_V2,
    "V3": SYSTEM_PROMPT_V3
}


# 3. Run a Single Experiment

def evaluate_case(test_case, prompt):

    context = {
        "user_task": test_case["user_task"],
        "tool_name": test_case["tool_name"],
        "tool_parameters": test_case["tool_parameters"],
        "agent_history": test_case["agent_history"]
    }

    start_time = time.time()

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "system",
                    "content": prompt
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        context,
                        ensure_ascii=False
                    )
                }
            ],
            temperature=0,
            max_tokens=300
        )

        latency = time.time() - start_time

        content = response.choices[0].message.content
        result = json.loads(content)

        decision = result.get("decision")
        reason = result.get("reason", "")

        valid_decisions = [
            "auto_approve",
            "auto_deny",
            "escalate"
        ]

        if decision not in valid_decisions:
            decision = "escalate"
            reason = "Invalid model output"

        usage = response.usage

        input_tokens = (
            usage.prompt_tokens if usage else 0
        )

        output_tokens = (
            usage.completion_tokens if usage else 0
        )

        return {
            "decision": decision,
            "reason": reason,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "latency": round(latency, 3),
            "status": "success"
        }

    except Exception as e:

        return {
            "decision": "escalate",
            "reason": "API or parsing error",
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "latency": round(time.time() - start_time, 3),
            "status": f"error: {type(e).__name__}"
        }


# 4. Run All Experiments

def run_experiments():

    results = []

    total = len(TEST_CASES) * len(PROMPTS)
    current = 0

    for version, prompt in PROMPTS.items():

        print(f"\nTesting Prompt {version}")

        for test_case in TEST_CASES:

            current += 1

            print(
                f"\n[{current}/{total}] "
                f"{version} - {test_case['id']}"
            )

            result = evaluate_case(
                test_case,
                prompt
            )

            expected = test_case["expected_decision"]

            correct = (
                result["status"] == "success"
                and result["decision"] == expected
            )

            row = {
                "prompt_version": version,
                "test_id": test_case["id"],
                "category": test_case["category"],
                "expected_decision": expected,
                "actual_decision": result["decision"],
                "correct": correct,
                "reason": result["reason"],
                "input_tokens": result["input_tokens"],
                "output_tokens": result["output_tokens"],
                "total_tokens": result["total_tokens"],
                "latency": result["latency"],
                "status": result["status"]
            }

            results.append(row)

            print("Expected:", expected)
            print("Actual:", result["decision"])
            print("Correct:", correct)
            print("Tokens:", result["total_tokens"])

            # Save results after every test
            save_results(results)

            time.sleep(0.5)

    print_summary(results)


# 5. Save CSV Results

def save_results(results):

    filename = RESULT_FILE

    if not results:
        return

    with open(
        filename,
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=list(results[0].keys())
        )

        writer.writeheader()
        writer.writerows(results)


# 6. Print Summary

def print_summary(results):

    print("\n" + "=" * 50)
    print("EXPERIMENT SUMMARY")
    print("=" * 50)

    for version in PROMPTS:

        version_results = [
            r for r in results
            if r["prompt_version"] == version
        ]

        successful = [
            r for r in version_results
            if r["status"] == "success"
        ]

        correct_count = sum(
            r["correct"] for r in successful
        )

        accuracy = (
            correct_count / len(successful)
            if successful else 0
        )

        total_tokens = sum(
            r["total_tokens"] for r in version_results
        )

        escalations = sum(
            r["actual_decision"] == "escalate"
            for r in successful
        )

        print(f"\nPrompt {version}")
        print(f"Successful API Calls: {len(successful)}")
        print(f"Accuracy: {accuracy:.2%}")
        print(f"Escalations: {escalations}")
        print(f"Total Tokens: {total_tokens}")

    print("\nResults saved to:")
    print(RESULT_FILE)


# 7. Main

if __name__ == "__main__":
    run_experiments()