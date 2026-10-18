"""Offline interface and gateway regression tests. No network or API key required."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pydantic import create_model
from agentdojo.functions_runtime import Function, FunctionCall, FunctionsRuntime
from approval_gate import Decision, ToolCallContext, ApprovalGate, Outcome
from semantic_adapter import SemanticPolicy
from semantic_policy import semantic_risk_assessment
from prompts import SYSTEM_PROMPT


def context():
    return ToolCallContext('probe', {}, 'Return a local test value', 'Run probe',
                           [{'role': 'user', 'content': 'Run probe'}], 0, 1)


class AdapterTests(unittest.TestCase):
    def test_selected_default_reaches_model(self):
        response = SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content='{"decision":"auto_approve"}'))])
        with patch('semantic_policy.get_client') as getter:
            create = getter.return_value.chat.completions.create
            create.return_value = response
            self.assertEqual(SemanticPolicy().decide(context()), Decision.APPROVE)
            self.assertEqual(create.call_args.kwargs['messages'][0]['content'], SYSTEM_PROMPT)
            self.assertEqual(semantic_risk_assessment('task', 'probe', {}, []), 'auto_approve')
            self.assertEqual(create.call_args.kwargs['messages'][0]['content'], SYSTEM_PROMPT)

    def test_mapping_and_context(self):
        for raw, expected in [('auto_approve', Decision.APPROVE),
                              ('auto_deny', Decision.DENY), ('escalate', Decision.ESCALATE),
                              ('invalid', Decision.ESCALATE), (None, Decision.ESCALATE)]:
            seen = {}
            def assess(**kwargs):
                seen.update(kwargs)
                return raw
            self.assertEqual(SemanticPolicy(assessor=assess).decide(context()), expected)
            self.assertEqual(seen['tool_description'], context().tool_description)
            self.assertEqual(json.loads(seen['agent_history'][0])['role'], 'user')
            self.assertNotIn('budget_remaining', seen)

    def test_assessor_failure(self):
        def broken(**kwargs):
            raise RuntimeError('offline failure')
        self.assertEqual(SemanticPolicy(assessor=broken).decide(context()), Decision.ESCALATE)

    def test_prompt_selection(self):
        for version in ['V1', 'V2', 'V3']:
            self.assertEqual(SemanticPolicy(version).prompt_version, version)
        with self.assertRaises(ValueError):
            SemanticPolicy('V4')

    def test_model_output_and_failure(self):
        for content, expected in [('{"decision":"auto_approve"}', 'auto_approve'),
                                  ('{"decision":"invalid"}', 'escalate'),
                                  ('[]', 'escalate'), ('not json', 'escalate')]:
            response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
            with patch('semantic_policy.get_client') as getter:
                getter.return_value.chat.completions.create.return_value = response
                self.assertEqual(semantic_risk_assessment('task', 'probe', {}, []), expected)
        with patch('semantic_policy.get_client', side_effect=RuntimeError('no key')):
            self.assertEqual(semantic_risk_assessment('task', 'probe', {}, []), 'escalate')

    def test_gateway_execution_and_budget(self):
        for raw, k, review, outcome, calls, reviews in [
            ('auto_approve', 1, True, Outcome.AUTO_APPROVED, 1, 0),
            ('auto_deny', 1, True, Outcome.AUTO_DENIED, 0, 0),
            ('escalate', 1, True, Outcome.HUMAN_APPROVED, 1, 1),
            ('escalate', 1, False, Outcome.HUMAN_DENIED, 0, 1),
            ('escalate', 0, True, Outcome.BUDGET_EXHAUSTED_DENIED, 0, 0),
        ]:
            executed = []
            reviewed = []
            def probe():
                executed.append(True)
                return 'ok'
            class Reviewer:
                def review(self, ctx):
                    reviewed.append(True)
                    return review
            fn = Function(name='probe', description='Local test', parameters=create_model('ProbeArgs'),
                          dependencies={}, run=probe, full_docstring='Local test', return_type=str)
            runtime = FunctionsRuntime([fn])
            gate = ApprovalGate(SemanticPolicy(assessor=lambda **kw: raw), Reviewer(), k)
            call = FunctionCall(function='probe', args={}, id='test-call')
            gate.query('Run probe', runtime, messages=[{'role': 'assistant', 'content': [], 'tool_calls': [call]}])
            self.assertEqual(gate.records[0].outcome, outcome.value)
            self.assertEqual(len(executed), calls)
            self.assertEqual(len(reviewed), reviews)
            self.assertEqual(gate.budget.remaining, k - reviews)
            gate.start_task()
            self.assertEqual(gate.budget.remaining, k)
            self.assertEqual(gate.records, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)

