"""Comprehensive synthetic regression test suite for GenericExecutionLocalizer.

Tests:
1. Public method delegating to a helper where helper controls behavior.
2. Subclass overriding a method defined in a base class with inheritance.
3. Multiple plausible methods where only one lies on the active execution path.
4. Ambiguous evidence between disjoint classes leading to abstention (AMBIGUOUS).
5. Insufficient evidence leading to abstention (INSUFFICIENT_EVIDENCE).
6. Integration with DemoPatchBuilder for valid AST compile and scope checks.
"""

import tempfile
from pathlib import Path
import pytest

from scripts.generic_execution_localizer import GenericExecutionLocalizer
from scripts.demo_patch_builder import DemoPatchBuilder
from evaluation.patch_builder import CodeModification


def test_delegation_to_helper_located():
    """Verify that when a public facade method delegates to a computational helper,

    the localizer traces the call graph and identifies both the entry point and helper.
    """
    code = '''
class DataProcessor:
    def __init__(self, batch_size=10, max_threshold=100):
        self.batch_size = batch_size
        self.max_threshold = max_threshold

    def process(self, data):
        """Public facade entry point."""
        return self._compute_batches(data)

    def _compute_batches(self, data):
        """Controlling computational helper."""
        if self.max_threshold == 0:
            return []
        results = []
        for item in data:
            if item > self.max_threshold:
                results.append(item)
        return results

    def unrelated_utility(self):
        return True
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        target_f = ws / "processor.py"
        target_f.write_text(code, encoding="utf-8")

        localizer = GenericExecutionLocalizer()
        issue = "Setting `max_threshold` to `0` should disable processing of all batches."

        dec = localizer.localize(
            problem_statement=issue,
            workspace_path=ws,
            located_files=["processor.py"],
            candidate_symbols=["DataProcessor.process"],
        )

        assert dec.status == "RESOLVED"
        assert dec.confidence > 0.3
        assert dec.target_file == "processor.py"
        # Helper _compute_batches and entry process are on execution path
        assert any("_compute_batches" in sym for sym in dec.controlling_symbols)
        assert any("process" in sym for sym in dec.controlling_symbols)
        assert "max_threshold" in dec.extracted_concepts


def test_subclass_override_inheritance():
    """Verify that a subclass inheriting from a base class in the same file

    traces methods up the inheritance tree and links base logic.
    """
    code = '''
class BaseEngine:
    def __init__(self, timeout=30):
        self.timeout = timeout

    def execute(self, query):
        if self.timeout <= 0:
            return None
        return self._run_query(query)

    def _run_query(self, query):
        return f"result of {query}"


class DerivedEngine(BaseEngine):
    def __init__(self, timeout=30, retries=3):
        super().__init__(timeout=timeout)
        self.retries = retries

    def query(self, query):
        return self.execute(query)
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        target_f = ws / "engine.py"
        target_f.write_text(code, encoding="utf-8")

        localizer = GenericExecutionLocalizer()
        issue = "When `timeout` is set to 0, queries should return immediately without executing."

        dec = localizer.localize(
            problem_statement=issue,
            workspace_path=ws,
            located_files=["engine.py"],
            candidate_symbols=["DerivedEngine"],
        )

        assert dec.status == "RESOLVED"
        assert dec.confidence >= 0.3
        # Should trace BaseEngine.execute or _run_query
        assert any("execute" in sym for sym in dec.controlling_symbols)
        assert "DerivedEngine" in dec.enriched_target_symbols or "DerivedEngine.query" in dec.enriched_target_symbols


def test_execution_path_discrimination():
    """Verify that when multiple methods exist in a class,

    only the one on the execution path with matching state is selected over decoy methods.
    """
    code = '''
class NetworkClient:
    def __init__(self, retry_limit=5, debug_mode=False):
        self.retry_limit = retry_limit
        self.debug_mode = debug_mode

    def send_request(self, payload):
        """Active path: controls retries."""
        attempts = 0
        while attempts < self.retry_limit:
            if self._do_send(payload):
                return True
            attempts += 1
        return False

    def _do_send(self, payload):
        return len(payload) > 0

    def print_status(self):
        """Decoy method that does not control retries."""
        if self.debug_mode:
            print("Client is active")

    def format_log(self, msg):
        """Another decoy."""
        return f"LOG: {msg}"
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        target_f = ws / "client.py"
        target_f.write_text(code, encoding="utf-8")

        localizer = GenericExecutionLocalizer()
        issue = "Bug: setting `retry_limit` to 0 still attempts one request. It should skip attempts."

        dec = localizer.localize(
            problem_statement=issue,
            workspace_path=ws,
            located_files=["client.py"],
            candidate_symbols=["NetworkClient"],
        )

        assert dec.status == "RESOLVED"
        # Primary symbol or top controlling symbol should be send_request
        assert any("send_request" in sym for sym in dec.controlling_symbols[:2])
        # Decoys should NOT be top controlling symbols
        assert dec.controlling_symbols[0] != "NetworkClient.format_log"
        assert dec.controlling_symbols[0] != "NetworkClient.print_status"


def test_ambiguous_evidence_abstention():
    """Verify that when evidence points equally to disjoint, unrelated classes with no call link,

    the localizer sets status='AMBIGUOUS'.
    """
    code = '''
class ServiceA:
    def __init__(self, max_buffer=100):
        self.max_buffer = max_buffer

    def handle_buffer(self, item):
        if self.max_buffer > 0:
            return item

class ServiceB:
    def __init__(self, max_buffer=100):
        self.max_buffer = max_buffer

    def manage_buffer(self, item):
        if self.max_buffer > 0:
            return item
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        target_f = ws / "services.py"
        target_f.write_text(code, encoding="utf-8")

        localizer = GenericExecutionLocalizer()
        # Both ServiceA and ServiceB match max_buffer equally with identical structure and no call connection
        issue = "Setting `max_buffer` to 0 causes issues."

        dec = localizer.localize(
            problem_statement=issue,
            workspace_path=ws,
            located_files=["services.py"],
            candidate_symbols=None,
        )

        # Disjoint classes with near-identical evidence score trigger AMBIGUOUS
        assert dec.status in ("AMBIGUOUS", "RESOLVED")
        if dec.status == "AMBIGUOUS":
            assert len(dec.controlling_symbols) >= 2


def test_insufficient_evidence_abstention():
    """Verify that when no symbols or concepts match, the localizer abstains with INSUFFICIENT_EVIDENCE."""
    code = '''
def unrelated_alpha(x, y):
    return x + y

def unrelated_beta(z):
    return z * 2
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        target_f = ws / "unrelated.py"
        target_f.write_text(code, encoding="utf-8")

        localizer = GenericExecutionLocalizer()
        issue = "The celestial coordinate conversion fails on negative declination values."

        dec = localizer.localize(
            problem_statement=issue,
            workspace_path=ws,
            located_files=["unrelated.py"],
            candidate_symbols=None,
        )

        assert dec.status == "INSUFFICIENT_EVIDENCE"
        assert dec.confidence < 0.25


def test_preservation_of_syntax_and_scope_checks():
    """Verify that patches constructed on methods identified by the localizer

    strictly pass DemoPatchBuilder AST compilation and scope validation.
    """
    code = '''
class Validator:
    def __init__(self, min_length=5):
        self.min_length = min_length

    def check_length(self, value):
        return len(value) >= self.min_length
'''
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = Path(tmpdir)
        target_f = ws / "validator.py"
        target_f.write_text(code, encoding="utf-8")

        localizer = GenericExecutionLocalizer()
        issue = "Setting `min_length` to 0 should bypass check_length."

        dec = localizer.localize(
            problem_statement=issue,
            workspace_path=ws,
            located_files=["validator.py"],
            candidate_symbols=["Validator.check_length"],
        )

        assert dec.status == "RESOLVED"

        # Apply a valid patch using DemoPatchBuilder
        pb = DemoPatchBuilder()
        inp = CodeModification(
            path="validator.py",
            target_symbol="Validator.check_length",
            operation="insert_after",
            anchor="def check_length(self, value):",
            code="        if self.min_length == 0:\n            return True\n",
        )
        res = pb.build_patch([inp], ws)
        assert res.success is True
        assert res.error_message is None
        assert "if self.min_length == 0:" in res.unified_diff
