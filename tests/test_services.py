import pytest
from apps.services.chat_aggregator import ChatAggregator
from apps.services.stream_aggregator import StreamAggregator
from apps.services.chat_adapter import FakeChatAdapter
from apps.services.stream_adapter import FakeStreamAdapter
from unittest.mock import MagicMock, AsyncMock

async def async_lambda():
    pass

@pytest.mark.asyncio
async def test_chat_aggregator_ingest():
    adapters = {"chaturbate": FakeChatAdapter()}
    aggregator = ChatAggregator(adapters=adapters)
    # Mock redis connection
    aggregator.connect_redis = async_lambda
    class MockRedis:
        async def sadd(self, *args): pass
        async def publish(self, *args): pass
    aggregator._r = MockRedis()

    msg = await aggregator.ingest_message(
        tenant_id="tenant1",
        platform="chaturbate",
        sender="user1",
        content="Hello!",
        msg_type="message"
    )

    assert msg["tenant_id"] == "tenant1"
    assert msg["platform"] == "chaturbate"
    assert msg["sender"] == "user1"
    assert msg["content"] == "Hello!"

    inbox = aggregator.get_unified_inbox("tenant1")
    assert len(inbox) == 1
    assert inbox[0]["id"] == msg["id"]

@pytest.mark.asyncio
async def test_stream_aggregator_trigger():
    adapter = FakeStreamAdapter()
    aggregator = StreamAggregator(adapter=adapter)
    # Mock redis connection
    aggregator.connect_redis = async_lambda
    class MockRedis:
        async def xadd(self, *args): pass
    aggregator._r = MockRedis()

    mock_db_session = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = []
    mock_db_session.execute = AsyncMock(return_value=mock_result)

    result = await aggregator.trigger_stream(
        stream_id="stream1",
        tenant_id="tenant1",
        target_platforms=["chaturbate", "stripchat"],
        db_session=mock_db_session
    )

    assert result["stream_id"] == "stream1"
    assert result["status"] == "active"
