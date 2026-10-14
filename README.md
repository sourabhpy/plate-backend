# Plate Backend

Plate Backend is the API service powering the Plate AI-Native Team Productivity Platform.
Built with Django 5.x, Django REST Framework, PostgreSQL / pgvector, and Google GenAI.

## Features
- **Authentication**: JWT access and refresh token authentication with workspace isolation.
- **Tasks & Drag-and-Drop**: Workspace tasks, member assignment, workflow columns (`inbox`, `todo`, `in_progress`, `in_review`, `done`), and full audit history.
- **Strict HTTP Polling Communications**: Slack-inspired channels and DMs with 2-second incremental polling via `after_id` monotonic cursors and `before_id` pagination. No WebSockets or SSE required.
- **Voice Messages & AI Task Extraction**: Browser voice notes and uploads with AI task extraction, workspace member attribution, and evidence quotes.
- **AI Document & Image Analysis**: Multimodal text extraction, executive summaries, risk identification, and suggested tasks.
- **AI Team Memory (RAG)**: Hybrid querying combining authoritative database records for live state and vector cosine similarity for historical context.
- **Notifications**: In-app notifications and email dispatch.

## Local Setup
1. Activate virtual environment and install dependencies:
   ```bash
   source env/bin/activate
   pip install -r requirements.txt
   ```
2. Copy environment variables:
   ```bash
   cp .env.example .env
   ```
   *(Configured with `GEMINI_MODEL_ID=gemini-3.1-flash-lite` for all AI tasks)*
3. Run migrations and seed initial data:
   ```bash
   python manage.py migrate
   python manage.py seed_plate_data
   ```
4. Run development server on `127.0.0.1:8000`:
   ```bash
   python manage.py runserver 127.0.0.1:8000
   ```

## Django Admin Portal
Access the administration interface at [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/):
- **Username**: `sourabh`
- **Email**: `saurabhsharmasg76@gmail.com`
- **Password**: `admin`
*(Django Admin uses username and password for authentication)*

## Running Backend Tests
Execute all unit and integration tests across all applications:
```bash
python manage.py test
```
For detailed descriptions of all test cases, multi-tenant security verification, and app-by-app commands, see [TESTING.md](file:///Users/sourabhsharma/Documents/plate/plate-backend/TESTING.md).

## Running with Docker
```bash
docker compose up -d --build
```
