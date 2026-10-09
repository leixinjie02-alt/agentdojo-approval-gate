import time
import json
from cost_tracker import CostTracker

class SweepRunner:
    """
    PE6203 Project 2 - Automated Experiment Sweeper (Member 5)
    Executes benchmark evaluation sweeps across different budget 'k' values and approval policies.
    """
    def __init__(self, task_ids: list):
        """
        :param task_ids: List of benchmark task IDs to evaluate.
        """
        self.task_ids = task_ids

    def run_single_experiment(self, k_budget: int, policy_type: str, tracker: CostTracker):
        """
        Simulates a full evaluation run under a specific configuration.
        :param k_budget: Escalation budget k (forces Auto-deny once exhausted).
        :param policy_type: Approval policy ('full-approve', 'full-escalate', 'our-policy').
        :param tracker: CostTracker instance to log API usage.
        :return: Safe task completion rate (TCR).
        """
        print(f"\n🚀 Launching Experiment: Policy=[{policy_type}], Budget k=[{k_budget}]...")
        
        successful_tasks = 0
        current_k = k_budget

        for task_id in self.task_ids:
            # 1. Simulate Agent inference
            tracker.log_api_call("agent", prompt_tokens=1000, completion_tokens=200)

            # 2. Simulate Policy evaluation
            if policy_type == "our-policy":
                tracker.log_api_call("policy", prompt_tokens=500, completion_tokens=50)
                # Simulate escalating to human reviewer
                if current_k > 0:
                    current_k -= 1
                    tracker.log_api_call("reviewer", prompt_tokens=800, completion_tokens=30)

            # Simulate task success check
            successful_tasks += 1

        tcr = successful_tasks / len(self.task_ids)
        return tcr

    def run_sweep(self, k_list: list, policies: list):
        """
        Executes grid-search sweeps over all budget 'k' values and policy variants.
        :param k_list: List of budget limits, e.g., [0, 1, 2, 5].
        :param policies: List of approval policies, e.g., ['full-approve', 'our-policy'].
        """
        all_results = []

        for policy in policies:
            for k in k_list:
                # Create a fresh tracker for each independent run
                tracker = CostTracker()
                
                tcr = self.run_single_experiment(k_budget=k, policy_type=policy, tracker=tracker)
                cost_info = tracker.calculate_cost(model_name="gpt-4o-mini")

                result_entry = {
                    "policy": policy,
                    "k_budget": k,
                    "tcr": round(tcr, 4),
                    "total_cost_usd": cost_info["total_cost_usd"],
                    "hitl_load": tracker.usage["reviewer"]["calls"],  # Escalation count
                    "breakdown": cost_info["breakdown"]
                }
                all_results.append(result_entry)
                
                # Print progress to console
                print(f"✅ Completed [{policy} | k={k}] -> TCR: {tcr:.2%}, Cost: ${cost_info['total_cost_usd']:.4f}, Escalations: {tracker.usage['reviewer']['calls']}")

        # Export raw experimental results to JSON for Week 3 visualization and sharing
        with open("sweep_results.json", "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=4, ensure_ascii=False)
        
        print("\n🎉 Automated Sweep Complete! Results saved to 'sweep_results.json'.")


# =========================================================
# 🧪 Test Script
# =========================================================
if __name__ == "__main__":
    # Mock task set for initial dry run
    mock_tasks = ["task_1", "task_2", "task_3", "task_4", "task_5"]
    
    sweeper = SweepRunner(task_ids=mock_tasks)
    
    # Define budget values (k) and policy variants to sweep
    test_k_list = [0, 1, 3]
    test_policies = ["full-approve", "our-policy"]
    
    # Execute benchmark sweep
    sweeper.run_sweep(k_list=test_k_list, policies=test_policies)