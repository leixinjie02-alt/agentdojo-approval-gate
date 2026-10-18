import json
from typing import Dict, Any

class CostTracker:
    """
    PE6203 Project 2 - API Token and Cost Accountant (Member 5)
    Tracks token consumption and calculates USD costs across three main roles:
    Agent execution, Policy evaluation, and Human Reviewer simulation.
    """
    def __init__(self, model_prices: Dict[str, Dict[str, float]] = None):
        """
        Initialize the pricing model and token usage counters.
        :param model_prices: Price dictionary per 1 million (1M) tokens in USD.
        """
        # Default pricing per 1M tokens (in USD $)
        # You can update these prices according to your API provider (e.g., OpenRouter)
        self.model_prices = model_prices or {
            "gpt-4o": {"input": 2.50, "output": 10.00},
            "gpt-4o-mini": {"input": 0.15, "output": 0.60},
            "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
            "default": {"input": 1.00, "output": 2.00}  # Fallback price
        }
        
        # Initialize token counters for all three roles
        self.usage = {
            "agent": {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0},
            "policy": {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0},
            "reviewer": {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
        }

    def log_api_call(self, role: str, prompt_tokens: int, completion_tokens: int):
        """
        Logs token usage for a single API call.
        :param role: Target role, must be 'agent', 'policy', or 'reviewer'.
        :param prompt_tokens: Number of input tokens.
        :param completion_tokens: Number of output tokens.
        """
        if role not in self.usage:
            raise ValueError(f"Unknown role: {role}. Allowed roles are: 'agent', 'policy', 'reviewer'")
        
        self.usage[role]["prompt_tokens"] += prompt_tokens
        self.usage[role]["completion_tokens"] += completion_tokens
        self.usage[role]["calls"] += 1

    def calculate_cost(self, model_name: str = "gpt-4o-mini") -> Dict[str, Any]:
        """
        Calculates total USD costs broken down by role based on the specified model.
        :param model_name: Model name to fetch pricing.
        :return: A dictionary containing cost breakdowns and total cost.
        """
        prices = self.model_prices.get(model_name, self.model_prices["default"])
        input_price_per_token = prices["input"] / 1_000_000.0
        output_price_per_token = prices["output"] / 1_000_000.0

        breakdown = {}
        total_cost = 0.0

        for role, data in self.usage.items():
            p_tokens = data["prompt_tokens"]
            c_tokens = data["completion_tokens"]
            
            cost = (p_tokens * input_price_per_token) + (c_tokens * output_price_per_token)
            total_cost += cost
            
            breakdown[role] = {
                "prompt_tokens": p_tokens,
                "completion_tokens": c_tokens,
                "total_tokens": p_tokens + c_tokens,
                "calls": data["calls"],
                "cost_usd": round(cost, 6)
            }

        return {
            "model_used": model_name,
            "total_cost_usd": round(total_cost, 6),
            "breakdown": breakdown
        }

    def print_summary(self, model_name: str = "gpt-4o-mini"):
        """Prints a clean, formatted cost breakdown table in the console."""
        result = self.calculate_cost(model_name)
        print("\n" + "="*65)
        print(f"📊 PE6203 Cost Breakdown Summary ({result['model_used']})")
        print("="*65)
        print(f"{'Role':<12} | {'Calls':<6} | {'Prompt Tokens':<14} | {'Comp Tokens':<12} | {'Cost ($)':<8}")
        print("-"*65)
        for role, info in result["breakdown"].items():
            print(f"{role.capitalize():<12} | {info['calls']:<6} | {info['prompt_tokens']:<14} | {info['completion_tokens']:<12} | ${info['cost_usd']:.4f}")
        print("-"*65)
        print(f"💰 Total Cost: ${result['total_cost_usd']:.6f}")
        print("="*65 + "\n")


# =========================================================
# 🧪 Test Script (Runs when executing this file directly)
# =========================================================
if __name__ == "__main__":
    tracker = CostTracker()

    # Simulate sample API calls
    tracker.log_api_call(role="agent", prompt_tokens=1500, completion_tokens=300)
    tracker.log_api_call(role="policy", prompt_tokens=800, completion_tokens=100)
    tracker.log_api_call(role="reviewer", prompt_tokens=1200, completion_tokens=50)

    # Output formatted summary
    tracker.print_summary(model_name="gpt-4o-mini")