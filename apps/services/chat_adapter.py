import abc
import httpx
from typing import Dict, Any, List

class ChatAdapter(abc.ABC):
    @abc.abstractmethod
    async def send_message(self, credentials: Dict[str, Any], recipient: str, content: str) -> bool:
        pass

    @abc.abstractmethod
    async def fetch_recent_messages(self, credentials: Dict[str, Any]) -> List[Dict[str, Any]]:
        pass

class ChaturbateChatAdapter(ChatAdapter):
    async def send_message(self, credentials: Dict[str, Any], recipient: str, content: str) -> bool:
        # Example using a fictional official API endpoint
        url = "https://chaturbate.com/api/chat/send"
        headers = {"Authorization": f"Bearer {credentials.get('api_key')}"}
        payload = {"to": recipient, "message": content}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                return response.status_code == 200
            except httpx.RequestError:
                return False

    async def fetch_recent_messages(self, credentials: Dict[str, Any]) -> List[Dict[str, Any]]:
        url = "https://chaturbate.com/api/chat/recent"
        headers = {"Authorization": f"Bearer {credentials.get('api_key')}"}

        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=headers)
                if response.status_code == 200:
                    return response.json().get("messages", [])
                return []
            except httpx.RequestError:
                return []

class FakeChatAdapter(ChatAdapter):
    def __init__(self):
        self.sent_messages = []
        self.mock_recent = []

    async def send_message(self, credentials: Dict[str, Any], recipient: str, content: str) -> bool:
        self.sent_messages.append({"recipient": recipient, "content": content})
        return True

    async def fetch_recent_messages(self, credentials: Dict[str, Any]) -> List[Dict[str, Any]]:
        return self.mock_recent
