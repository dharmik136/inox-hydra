"""
Unit tests for Model Gateway async execution and SSE streaming.
================================================================
Verifies non-blocking async LLM completion and multi-provider token
streaming (OpenAI, Gemini, Anthropic, local deterministic).

Strict Invariants:
- Zero em-dashes across all code and docstrings.
- Strict zero cloud egress during tests.
"""

import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from studio.backend.agno_agentos.model_gateway import (
    AIProviderConfig,
    execute_llm_completion_async,
    stream_llm_completion_async
)


@pytest.mark.anyio
async def test_async_completion_local_deterministic_zero_egress():
    """Verifies that local deterministic engine returns empty string without network calls."""
    cfg = AIProviderConfig(provider="local_deterministic")
    result = await execute_llm_completion_async(cfg, "Write a hook")
    assert result == ""


@pytest.mark.anyio
async def test_stream_completion_local_deterministic_zero_egress():
    """Verifies that streaming local deterministic engine yields empty without network calls."""
    cfg = AIProviderConfig(provider="local_deterministic")
    chunks = []
    async for chunk in stream_llm_completion_async(cfg, "Write a hook"):
        chunks.append(chunk)
    assert chunks == [""]


@pytest.mark.anyio
async def test_async_completion_openai_mock(monkeypatch):
    """Verifies OpenAI-compatible async completion parsing."""
    cfg = AIProviderConfig(
        provider="openai",
        api_key="sk-test-mock-key-12345678",
        model="gpt-4o",
        base_url="https://api.openai.com/v1"
    )

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={
        "choices": [{"message": {"content": "Async hook response"}}]
    })

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    # Allow egress for test
    monkeypatch.setattr("studio.backend.egress.require", lambda url, cat: None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        res = await execute_llm_completion_async(cfg, "Write a test hook")
        assert res == "Async hook response"


@pytest.mark.anyio
async def test_stream_completion_openai_mock(monkeypatch):
    """Verifies OpenAI SSE streaming token chunk yielding."""
    cfg = AIProviderConfig(
        provider="openai",
        api_key="sk-test-mock-key-12345678",
        model="gpt-4o",
        base_url="https://api.openai.com/v1"
    )

    sse_lines = [
        'data: {"choices": [{"delta": {"content": "First "}}]}',
        'data: {"choices": [{"delta": {"content": "Second "}}]}',
        'data: {"choices": [{"delta": {"content": "Third"}}]}',
        'data: [DONE]'
    ]

    async def mock_aiter_lines():
        for line in sse_lines:
            yield line

    mock_resp = MagicMock()
    mock_resp.aiter_lines = mock_aiter_lines

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr("studio.backend.egress.require", lambda url, cat: None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        chunks = []
        async for chunk in stream_llm_completion_async(cfg, "Write a stream hook"):
            chunks.append(chunk)

        assert chunks == ["First ", "Second ", "Third"]


@pytest.mark.anyio
async def test_stream_completion_gemini_mock(monkeypatch):
    """Verifies Gemini SSE streaming token chunk yielding."""
    cfg = AIProviderConfig(
        provider="gemini",
        api_key="AIzaSy_mock_gemini_key",
        model="gemini-2.5-flash",
        base_url="https://generativelanguage.googleapis.com/v1beta"
    )

    sse_lines = [
        'data: {"candidates": [{"content": {"parts": [{"text": "Gemini "}]}}]}',
        'data: {"candidates": [{"content": {"parts": [{"text": "Stream "}]}}]}',
        'data: {"candidates": [{"content": {"parts": [{"text": "Done"}]}}]}'
    ]

    async def mock_aiter_lines():
        for line in sse_lines:
            yield line

    mock_resp = MagicMock()
    mock_resp.aiter_lines = mock_aiter_lines

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr("studio.backend.egress.require", lambda url, cat: None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        chunks = []
        async for chunk in stream_llm_completion_async(cfg, "Generate Gemini post"):
            chunks.append(chunk)

        assert chunks == ["Gemini ", "Stream ", "Done"]


@pytest.mark.anyio
async def test_stream_completion_anthropic_mock(monkeypatch):
    """Verifies Anthropic SSE streaming token chunk yielding."""
    cfg = AIProviderConfig(
        provider="anthropic",
        api_key="sk-ant-mock-key-12345",
        model="claude-3-5-sonnet-20241022",
        base_url="https://api.anthropic.com/v1"
    )

    sse_lines = [
        'event: content_block_delta',
        'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Claude "}}',
        'event: content_block_delta',
        'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Token"}}'
    ]

    async def mock_aiter_lines():
        for line in sse_lines:
            yield line

    mock_resp = MagicMock()
    mock_resp.aiter_lines = mock_aiter_lines

    mock_stream_ctx = AsyncMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_client = AsyncMock()
    mock_client.stream = MagicMock(return_value=mock_stream_ctx)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    monkeypatch.setattr("studio.backend.egress.require", lambda url, cat: None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        chunks = []
        async for chunk in stream_llm_completion_async(cfg, "Generate Claude post"):
            chunks.append(chunk)

        assert chunks == ["Claude ", "Token"]


def test_stream_ai_endpoint_sse_contract():
    """Verifies that POST /api/ai/stream returns text/event-stream with SSE chunks."""
    from studio.backend.app import app
    from studio.backend.security import get_or_create_token, TOKEN_HEADER
    from fastapi.testclient import TestClient

    client = TestClient(app)
    token = get_or_create_token()
    response = client.post(
        "/api/ai/stream",
        headers={TOKEN_HEADER: token},
        json={"prompt": "Architecture design"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert "data: [DONE]" in response.text

