"""Tests for Agent output validation and schema compliance."""

import unittest
from agents.base import AgentInputMetadata
from agents.coder import CoderAgent, CoderOutput
from agents.locator import LocatorAgent, LocatorOutput
from agents.supervisor import SupervisorAgent, SupervisorDecision
from agents.tester import TesterAgent, TesterOutput
from models.base import ModelConfig
from models.providers import MockModelProvider


class TestAgents(unittest.TestCase):
    def setUp(self):
        self.locator_cfg = ModelConfig(name="Locator", model_id="mock-locator")
        self.coder_cfg = ModelConfig(name="Coder", model_id="mock-coder")
        self.tester_cfg = ModelConfig(name="Tester", model_id="mock-tester")
        self.supervisor_cfg = ModelConfig(name="Supervisor", model_id="mock-supervisor")

        self.metadata = AgentInputMetadata(task_id="test-1", run_id="run-1", attempt=1)

    def test_locator_agent_valid_output(self):
        provider = MockModelProvider(self.locator_cfg)
        agent = LocatorAgent(provider)
        res = agent.execute({"issue": "Test issue", "repo_structure": "src/"}, self.metadata)
        self.assertTrue(res.success)
        self.assertIsInstance(res.output, LocatorOutput)
        self.assertGreaterEqual(res.confidence, 0.0)
        self.assertLessEqual(res.confidence, 1.0)
        self.assertIn("src/calculator.py", res.output.relevant_files)

    def test_coder_agent_valid_output(self):
        provider = MockModelProvider(self.coder_cfg)
        agent = CoderAgent(provider)
        res = agent.execute({"issue": "Test issue", "locator_result": {}}, self.metadata)
        self.assertTrue(res.success)
        self.assertIsInstance(res.output, CoderOutput)
        self.assertTrue(len(res.output.patch) > 0)
        self.assertIn("src/calculator.py", res.output.modified_files)

    def test_tester_agent_valid_output(self):
        provider = MockModelProvider(self.tester_cfg)
        agent = TesterAgent(provider)
        res = agent.execute({"issue": "Test issue", "candidate_patch": "diff"}, self.metadata)
        self.assertTrue(res.success)
        self.assertIsInstance(res.output, TesterOutput)
        self.assertGreater(len(res.output.recommended_tests), 0)

    def test_supervisor_agent_valid_output(self):
        provider = MockModelProvider(self.supervisor_cfg)
        agent = SupervisorAgent(provider)
        res = agent.execute({"task_id": "test-1", "issue": "Test issue"}, self.metadata)
        self.assertTrue(res.success)
        self.assertIsInstance(res.output, SupervisorDecision)
        self.assertTrue(res.output.should_retry)
        self.assertIn(res.output.detected_failure, ["F1", "F2", "F3", "F4"])


if __name__ == "__main__":
    unittest.main()
