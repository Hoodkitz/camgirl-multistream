import pytest
from apps.services.stream_adapter import FakeStreamAdapter, FfmpegStreamAdapter
from unittest.mock import patch, MagicMock

def test_fake_stream_adapter():
    adapter = FakeStreamAdapter()
    ingest_url = "rtmp://localhost/live/test"
    output_urls = ["rtmp://out1", "rtmp://out2"]

    assert adapter.start_stream(ingest_url, output_urls) == True
    assert ingest_url in adapter.active_streams

    assert adapter.stop_stream(ingest_url) == True
    assert ingest_url not in adapter.active_streams

@patch('subprocess.Popen')
def test_ffmpeg_stream_adapter(mock_popen):
    adapter = FfmpegStreamAdapter()
    ingest_url = "rtmp://localhost/live/test"
    output_urls = ["rtmp://out1"]

    mock_process = MagicMock()
    mock_popen.return_value = mock_process

    assert adapter.start_stream(ingest_url, output_urls) == True
    mock_popen.assert_called_once()
    assert ingest_url in adapter._processes

    assert adapter.stop_stream(ingest_url) == True
    mock_process.terminate.assert_called_once()
    assert ingest_url not in adapter._processes
