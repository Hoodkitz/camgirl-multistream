# Multi-Stream & Chat-Aggregation (CamGirl Multi-Stream)

Ein Feed per OBS → gleichzeitig an alle Cam-Portale. Alle Portal-Chats gebündelt in einer App.

## Was funktioniert (v0.2)

| Bereich | Umsetzung |
|---|---|
| **Portal-Zugangsdaten** | `POST /api/v1/credentials` – AES-256-GCM Envelope Encryption, DEK pro Eintrag, AAD = `tenant:platform`, KEK pro Mandant. Klartext verlässt nie die API. |
| **Stream-Keys** | `POST /api/v1/streams/keys` – Key wird einmalig angezeigt, nur SHA-256 gespeichert, widerrufbar. RTMP- und SRT-URL. |
| **SRS-Integration** | `POST /api/v1/streams/verify` (Header `X-SRS-Secret`, IP-Allowlist): `on_publish` (Key + Quota), `on_forward` (Ziel-URLs mit entschlüsselten Portal-Keys), `on_unpublish`. `POST /api/v1/streams/overdue` = 24h-Wall-Time-Cap. |
| **Quotas** | Standard: 1 Feed / 3 Ziele, Pro: 1 / 10, Agentur: 3 / 10 |
| **Chat-Ingest** | `POST /api/v1/events` (Connector-Secret), normalisiertes Event-Schema, idempotent über `event_id` |
| **Posteingang** | `GET /api/v1/chat/inbox` (Filter Plattform, Replay via `since_id`), `GET /api/v1/chat/tabs` (ein Reiter pro Portal) |
| **Live-Feed** | `POST /api/v1/ws/ticket` → `WS /ws/v1/chat?ticket=…` (Einmal-Ticket, 30 s), Heartbeat alle 30 s |
| **Antworten** | `POST /api/v1/chat/reply` → Transactional Outbox → Portal-Connector (Backoff + Jitter, Dead-Letter nach 8 Versuchen) |
| **Auto-Begrüßung** | `PUT /api/v1/automation` – Vorlage mit `{username}`/`{platform}`, Cooldown pro Zuschauer, Plattformfilter |
| **Spendenziel** | Token-Ziel pro Session → signierter OBS-Webhook (HMAC) über die Outbox |
| **Statistiken** | `GET /api/v1/stats/overview` – Umsatz, Tokens, Tips, Chatter, Top-Spender pro Portal, Umsatz/Stunde |
| **Abo** | `POST /api/v1/webhooks/stripe` – HMAC-Prüfung, Inbox mit UNIQUE `event_id`, setzt Tarif |
| **DSGVO** | `DELETE /api/v1/tenants/me` – Re-Auth (≤ 5 min) + Namensbestätigung, Crypto-Shredding des KEK (KEKs liegen außerhalb der DB in `KEY_STORE_DIR`, das nicht mit der DB gesichert werden darf; Produktion: Cloud-KMS/HSM), physische Löschkaskade. `POST /api/v1/maintenance/retention` löscht Chats nach 30 Tagen. |
| **SSRF-Schutz** | OBS-Webhooks nur https auf öffentliche Hosts (beim Speichern und beim Senden geprüft, keine Redirects); Ingest-URLs nur zu bekannten Portal-Hosts (`EXTRA_INGEST_HOSTS`), Port 1935/443 |
| **Sicherheit** | JWT (OIDC-Tokens, 15 min), RBAC (owner/creator/agent/audit), Mandantenfilter in jeder Abfrage + Postgres-RLS (`db_migrations/001_rls.sql`), Rate-Limit 60/min, ENV default `prod` (bricht ohne echte Secrets ab) |

## Start

```bash
uv venv -p 3.12 .venv && uv pip install -p .venv/bin/python -r requirements.txt pytest
ENV=dev .venv/bin/uvicorn apps.api.main:app --reload   # /docs, /dev/token
.venv/bin/python -m pytest                              # 25 Tests
docker build -t camgirl-multistream .
```

## Noch offen

- Echte Portal-Connectoren (Chat lesen/schreiben je Portal) – aktuell `RecordingConnector`
- SRS-Deployment (Konfig mit `http_hooks` + `forward backend` auf `/api/v1/streams/verify`)
- Cloud-KMS statt `LocalKMS`, Redis statt In-Memory-Bus/Rate-Limit für Mehrknotenbetrieb
- Alembic-Migrationen, Mobile-App (React Native/Flutter), Push-Notifications
