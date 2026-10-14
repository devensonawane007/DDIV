"""Regression tests for LoggerWriter UTF-8 console and log handling on Windows."""

import tempfile
from pathlib import Path
from scripts.run_experiment_worker import LoggerWriter


class StrictCP1252Stream:
    """Simulates a Windows console stream with strict cp1252 encoding."""

    def __init__(self):
        self.encoding = "cp1252"
        self.written_chunks = []

    def write(self, text: str):
        # Strict cp1252 encoding check to emulate console failure on non-mappable characters
        text.encode("cp1252", errors="strict")
        self.written_chunks.append(text)

    def flush(self):
        pass


def test_logger_writer_handles_unicode_characters_without_crashing():
    """Verify LoggerWriter handles non-cp1252 unicode without raising and preserves UTF-8 log."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "worker.log"
        mock_console = StrictCP1252Stream()

        writer = LoggerWriter(mock_console, log_path)

        # Test string containing \u2011, em dash (\u2014), and curly quotes (\u201c, \u201d)
        special_string = "Tester recommends: opt\u2011in \u2014 \u201cstrict validation\u201d\n"

        # 1. Writing to writer must NOT raise UnicodeEncodeError
        writer.write(special_string)
        writer.flush()
        writer.close()

        # 2. Console stream received safely handled text without crashing
        assert len(mock_console.written_chunks) == 1
        # In console stream, unmapped char (\u2011) was replaced gracefully
        assert "?" in mock_console.written_chunks[0] or "opt" in mock_console.written_chunks[0]

        # 3. UTF-8 log file preserved the exact pristine characters
        log_content = log_path.read_text(encoding="utf-8")
        assert special_string == log_content
        assert "\u2011" in log_content
        assert "\u2014" in log_content
        assert "\u201c" in log_content
        assert "\u201d" in log_content


def test_logger_writer_standard_stream():
    """Verify LoggerWriter standard write and flush with normal unicode."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "worker2.log"
        captured = []

        class NormalStream:
            def __init__(self):
                self.encoding = "utf-8"

            def write(self, s):
                captured.append(s)

            def flush(self):
                pass

        writer = LoggerWriter(NormalStream(), log_path)
        writer.write("Standard test \u2014 passes cleanly\n")
        writer.close()

        assert "Standard test \u2014 passes cleanly\n" in captured
        assert log_path.read_text(encoding="utf-8") == "Standard test \u2014 passes cleanly\n"
