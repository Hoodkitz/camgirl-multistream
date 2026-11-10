# CamGirl Multi-Stream SaaS MVP

A unified backend API for erotic models/camgirls to stream to multiple portals simultaneously and manage chats from a single interface.

## Prerequisites
- Docker and Docker Compose
- Python 3.12+
- ffmpeg (required for restreaming functionality)

## Setup

1. **Environment Variables**:
   Copy `.env.example` (or create a `.env` file) in the project root with the following:
   ```env
   DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/camgirl
   JWT_SECRET=your_super_secret_jwt_key
   CREDENTIALS_KEY=uE2r1pXw7mS0G4c5B8hQ6iL9kV3fD1zA_yR2vO5xT8w=
   REDIS_URL=redis://localhost:6379
   ```
   *(Note: The `CREDENTIALS_KEY` must be a valid 32 url-safe base64-encoded byte string for Fernet encryption).*

2. **Start Infrastructure**:
   Spin up PostgreSQL and Redis using Docker Compose:
   ```bash
   docker compose up -d
   ```

3. **Install Dependencies** (Local Dev):
   ```bash
   pip install -r requirements.txt
   ```

4. **Database Migrations**:
   We use Alembic for async database migrations. Initialize the database schema:
   ```bash
   alembic upgrade head
   ```

5. **Run the Application**:
   Start the FastAPI development server:
   ```bash
   uvicorn apps.api.main:app --reload
   ```

## Architecture

- **Auth & Multi-tenancy**: Uses JWT and Argon2 for passwords. Endpoints are guarded with tenant isolation and Role-Based Access Control (RBAC).
- **Database**: PostgreSQL with asyncpg, models via SQLAlchemy mapped by UUIDs for multi-tenancy. Stream credentials are encrypted at rest using Fernet.
- **Multi-Stream**: Driven by `FfmpegStreamAdapter` (via the `StreamAggregator`), utilizing ffmpeg's copy codec for fan-out broadcasting to multiple portals.
- **Chat Bundling**: Integrates via the `ChatAggregator` using simulated webhooks and standard HTTP calls mapped through specific `ChatAdapters` for portals like Chaturbate and Stripchat.

## Testing

Tests are written using `pytest` and utilize `pytest-asyncio` with an in-memory SQLite database (`aiosqlite`) to keep tests completely stateless and isolated.

To run the full test suite:
```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
pytest tests/
```

To run with verbose output:
```bash
pytest tests/ -v
```
