# Plate Backend

Plate Backend is the high-performance API service powering the Plate AI-Native Team Productivity Platform.
Built with Django 5.x, Django REST Framework, PostgreSQL / pgvector (with SQLite dev fallback), and Google GenAI (`gemini-3.8-flash` / `gemini-3.1-flash-lite`).

---

## Features

- **Authentication & Multi-Tenancy**: JWT access and refresh token authentication with strict header-based workspace isolation (`X-Workspace-ID`).
- **Tasks & Drag-and-Drop Kanban**: Full workflow lifecycle (`inbox`, `todo`, `in_progress`, `in_review`, `done`), team member column stacks, drag-and-drop position reordering, and immutable `TaskActivity` audit history.
- **Strict HTTP Polling Communications**: Slack-inspired channels, direct messages, and private group conversations with 2-second incremental polling via `after_id` monotonic cursors and `before_id` pagination. Strictly zero WebSockets or SSE dependencies.
- **Voice Messages & AI Task Extraction**: Browser voice notes and uploads with AI task extraction, workspace member attribution, and evidence quotes.
- **AI Document & Image Analysis**: Multimodal text extraction, executive summaries, risk identification, and suggested tasks. Analyzed documents are automatically indexed into Team Memory RAG.
- **Admin-Only AI Operations History**: Complete historical record of all voice transcriptions and document analyses. Accessible only to workspace administrators via `/api/ai/history/`.
- **Media Validation & Security**:
  - **File Size Limit**: Media uploads larger than 5MB are strictly rejected across all endpoints (`core/media_validators.py`).
  - **Video Prohibition**: Video files (`video/*`, `.mp4`, `.mov`, `.avi`, etc.) are prohibited application-wide.
  - **Audio Duration Limit**: Audio analysis enforces a maximum duration of 1 minute (60 seconds) and accepts only a single file at a time.
- **AI Team Memory (RAG)**: Hybrid querying combining authoritative database records for live state and vector cosine similarity for historical context.
- **Notifications**: Real-time in-app notification center and HTML email dispatch.

---

## Local Setup

1. **Activate virtual environment and install dependencies**:
   ```bash
   source env/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure environment variables**:
   ```bash
   cp .env.example .env
   ```
   *(Configured with `GEMINI_MODEL_ID=gemini-3.1-flash-lite` for all AI tasks)*

3. **Run migrations and seed initial data**:
   ```bash
   python manage.py migrate
   python manage.py seed_plate_data
   ```

4. **Start the development server on `127.0.0.1:8000`**:
   ```bash
   python manage.py runserver 127.0.0.1:8000
   ```

---

## Django Admin Portal

Access the administration portal at [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/):
- **Username**: `admin`
- **Email**: `admin@acme.com`
- **Password**: `admin`

*(Django Admin uses username and password for authentication)*

---

## Running Backend Tests

Execute all 33 automated unit and integration tests across all applications:
```bash
python manage.py test
```

Target individual applications during active development:
```bash
python manage.py test core
python manage.py test tasks
python manage.py test communications
python manage.py test ai_services
python manage.py test notifications
```

For detailed descriptions of all test cases, multi-tenant security verification, and media validator tests, see [TESTING.md](./TESTING.md).

---

## Running with Docker

```bash
docker compose up -d --build
```
