import abc
import subprocess
from typing import List

class StreamAdapter(abc.ABC):
    @abc.abstractmethod
    def start_stream(self, ingest_url: str, output_urls: List[str]) -> bool:
        pass

    @abc.abstractmethod
    def stop_stream(self, stream_id: str) -> bool:
        pass

class FfmpegStreamAdapter(StreamAdapter):
    def __init__(self):
        self._processes = {}

    def start_stream(self, ingest_url: str, output_urls: List[str]) -> bool:
        command = ["ffmpeg", "-i", ingest_url, "-c", "copy"]
        for url in output_urls:
            command.extend(["-f", "flv", url])

        try:
            # We use subprocess.Popen to start the process in the background
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # In a real system, you would track process IDs and map them to stream IDs
            # Here we just keep a reference for stopping
            self._processes[ingest_url] = process
            return True
        except Exception as e:
            print(f"Error starting ffmpeg: {e}")
            return False

    def stop_stream(self, stream_id: str) -> bool:
        # Simplistic approach to stopping the process, assuming ingest_url = stream_id for mapping here
        if stream_id in self._processes:
            process = self._processes.pop(stream_id)
            process.terminate()
            return True
        return False

class FakeStreamAdapter(StreamAdapter):
    def __init__(self):
        self.active_streams = set()

    def start_stream(self, ingest_url: str, output_urls: List[str]) -> bool:
        self.active_streams.add(ingest_url)
        return True

    def stop_stream(self, stream_id: str) -> bool:
        if stream_id in self.active_streams:
            self.active_streams.remove(stream_id)
            return True
        return False
