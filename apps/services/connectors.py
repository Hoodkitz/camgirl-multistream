"""Ausgehende Portal-Connectoren (Chat-Antworten).

Die Cam-Portale bieten keine einheitliche oeffentliche Chat-API; je Portal wird ein
Adapter implementiert, der die entschluesselten Zugangsdaten nur im Speicher nutzt.
`RecordingConnector` ist der Default fuer dev/test und protokolliert Sendungen.
"""
from typing import Protocol


class ChatConnector(Protocol):
    async def send(self, platform: str, account: str, credentials: bytes, recipient: str | None, text: str) -> None: ...


class RecordingConnector:
    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, platform, account, credentials, recipient, text):
        self.sent.append({"platform": platform, "account": account, "recipient": recipient, "text": text})


connector: ChatConnector = RecordingConnector()
