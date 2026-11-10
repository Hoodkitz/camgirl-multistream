import pytest
from apps.services.chat_adapter import FakeChatAdapter, ChaturbateChatAdapter
from httpx import Response
from unittest.mock import patch

@pytest.mark.asyncio
async def test_fake_chat_adapter():
    adapter = FakeChatAdapter()
    creds = {"api_key": "fake"}

    success = await adapter.send_message(creds, "user1", "hello")
    assert success == True
    assert len(adapter.sent_messages) == 1
    assert adapter.sent_messages[0]["recipient"] == "user1"

    recent = await adapter.fetch_recent_messages(creds)
    assert recent == []

@pytest.mark.asyncio
@patch('httpx.AsyncClient.post')
async def test_chaturbate_adapter_send(mock_post):
    adapter = ChaturbateChatAdapter()
    creds = {"api_key": "test_key"}

    mock_post.return_value = Response(200)

    success = await adapter.send_message(creds, "user1", "hello")
    assert success == True
    mock_post.assert_called_once()

@pytest.mark.asyncio
@patch('httpx.AsyncClient.get')
async def test_chaturbate_adapter_fetch(mock_get):
    adapter = ChaturbateChatAdapter()
    creds = {"api_key": "test_key"}

    mock_get.return_value = Response(200, json={"messages": [{"id": 1, "text": "test"}]})

    messages = await adapter.fetch_recent_messages(creds)
    assert len(messages) == 1
    assert messages[0]["text"] == "test"
