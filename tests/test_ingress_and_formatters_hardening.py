import os
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

# Ensure studio/backend is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "studio", "backend"))

from formatters import (
    to_sans_bold,
    to_sans_italic,
    to_monospace,
    to_strikethrough,
    to_serif_bold,
    to_serif_italic,
    to_blackboard_bold,
    to_underline,
    to_circled_numbers,
    calculate_dwell_metrics,
    clean_text_formatting,
    analyze_hook,
    MAX_FORMAT_TEXT_LENGTH,
)
from ingress import (
    IngressMessageParser,
    TelegramIngressDaemon,
)


def test_formatters_null_and_non_string_handled():
    """Formatters should safely handle None, ints, floats, lists without throwing TypeError."""
    assert to_sans_bold(None) == ""
    assert to_sans_italic(None) == ""
    assert to_monospace(None) == ""
    assert to_strikethrough(None) == ""
    assert to_serif_bold(None) == ""
    assert to_serif_italic(None) == ""
    assert to_blackboard_bold(None) == ""
    assert to_underline(None) == ""
    assert to_circled_numbers(None) == ""

    # Non-string types
    assert len(to_sans_bold(12345)) > 0
    assert len(to_monospace(99.9)) > 0
    assert len(to_circled_numbers(1234)) > 0


def test_formatters_huge_text_bounded():
    """Text larger than MAX_FORMAT_TEXT_LENGTH (50k) is safely bounded."""
    huge_text = "A" * 100000
    res = to_sans_bold(huge_text)
    assert len(res) == MAX_FORMAT_TEXT_LENGTH


def test_clean_text_formatting_em_dashes():
    """clean_text_formatting strips em-dashes and en-dashes dynamically."""
    em_dash = chr(0x2014)
    en_dash = chr(0x2013)
    text = f"Architecture{em_dash}first principles{en_dash}always"
    cleaned = clean_text_formatting(text)
    assert em_dash not in cleaned
    assert en_dash not in cleaned
    assert "Architecture, first principles, always" == cleaned


def test_analyze_hook_null_and_empty():
    """analyze_hook returns expected defaults when provided None or empty strings."""
    for empty_input in (None, "", "   ", "\n\n"):
        res = analyze_hook(empty_input)
        assert res["score"] == 0
        assert res["hook_archetype"] == "Empty"
        assert res["char_count"] == 0
        assert res["mobile_safe"] is True
        assert res["desktop_safe"] is True


def test_calculate_dwell_metrics_null_and_empty():
    """calculate_dwell_metrics handles None and empty inputs cleanly."""
    for empty_input in (None, "", "  "):
        res = calculate_dwell_metrics(empty_input)
        assert res["dwell_status"] == "EMPTY"
        assert res["word_count"] == 0
        assert res["estimated_reading_sec"] == 0.0


def test_ingress_parser_null_and_empty():
    """IngressMessageParser handles None and non-string inputs safely."""
    metrics = IngressMessageParser.calculate_fold_metrics(None)
    assert metrics["total_chars"] == 0
    assert metrics["lines_above_fold"] == 0
    assert metrics["is_pre_fold_safe"] is True

    parsed = IngressMessageParser.parse_message(None)
    assert parsed["title"] == "Untitled Mobile Ingress"
    assert parsed["char_count"] == 0


def test_ingress_parser_em_dash_sanitized():
    """IngressMessageParser dynamically sanitizes em-dashes to avoid DB pollution."""
    em_dash = chr(0x2014)
    input_text = f"Title line\nThought text{em_dash}important detail"
    parsed = IngressMessageParser.parse_message(input_text)
    assert em_dash not in parsed["raw_content"]
    assert " -- " in parsed["raw_content"]


def test_ingress_daemon_stop_worker_responsive(monkeypatch):
    """Ingress daemon worker terminates immediately when stop_worker() is called."""
    daemon = TelegramIngressDaemon(bot_token="fake-token-test")
    monkeypatch.setattr(daemon, "poll_once", lambda: time.sleep(0.01))
    daemon.start_worker()
    assert daemon.is_running is True

    start_time = time.time()
    daemon.stop_worker()
    stop_duration = time.time() - start_time

    assert daemon.is_running is False
    # Stopping should take less than 1.5 seconds, proving responsive stop_event
    assert stop_duration < 1.5



def test_ingress_daemon_429_rate_limit_handled():
    """Ingress daemon extracts retry_after parameter upon HTTP 429 response."""
    daemon = TelegramIngressDaemon(bot_token="test-token")
    mock_res = MagicMock()
    mock_res.status_code = 429
    mock_res.json.return_value = {
        "ok": False,
        "error_code": 429,
        "description": "Too Many Requests: retry after 25",
        "parameters": {"retry_after": 25},
    }

    with patch("requests.get", return_value=mock_res):
        daemon.poll_once()
        assert daemon.current_delay >= 25.0
        assert "Rate limited" in daemon.last_error


def test_ingress_daemon_malformed_update_ignored():
    """Malformed non-dict updates or messages are safely skipped."""
    daemon = TelegramIngressDaemon(bot_token="test-token")
    assert daemon.process_incoming_update(None) is None
    assert daemon.process_incoming_update("string_update") is None
    assert daemon.process_incoming_update({"message": "not_a_dict"}) is None


def test_zero_em_dash_compliance_ingress_formatters():
    """Verify zero em-dash (0x2014) characters exist in ingress, formatters, and this test."""
    em_dash = chr(0x2014)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_files = [
        os.path.join(base_dir, "studio", "backend", "ingress.py"),
        os.path.join(base_dir, "studio", "backend", "formatters.py"),
        os.path.abspath(__file__),
    ]

    for file_path in target_files:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert em_dash not in content, f"Em-dash found in {file_path}"
