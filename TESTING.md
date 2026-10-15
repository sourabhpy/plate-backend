# Plate Backend Testing Documentation

This document describes the test suite architecture, coverage, execution methods, and testing patterns for the Plate Backend API.

---

## 1. Test Architecture Overview

The Plate backend test suite is built with the native **Django Test Framework** (`django.test.TestCase`) and **Django REST Framework Test Client** (`rest_framework.test.APIClient`).

### Key Testing Principles
- **Database Isolation**: Each test runs inside an isolated database transaction that rolls back automatically upon completion.
- **Multi-Tenant Workspace Security**: All endpoints enforce header-based tenant isolation via `X-Workspace-ID`. Tests verify cross-tenant access denial (`HTTP 403 Forbidden`).
- **Media Upload Validation**: Strict 5MB file limits, video upload prohibition, and 60-second audio duration limits are rigorously verified across all endpoints.
- **Role-Based Access Control**: AI history endpoints are tested to guarantee that standard members cannot view AI operational history while workspace admins have full visibility.
- **Resilient AI Mocking & Fallbacks**: The AI services are designed with deterministic rule-based and vector fallbacks. Tests run reliably in CI and offline environments without external network dependencies.
- **Authentication**: JWT token authentication and `APIClient.force_authenticate(user)` are used to simulate authenticated user workflows.

---

## 2. Environment Activation

Before running tests, ensure your virtual environment is activated from the `plate-backend` directory:

```bash
# Activate the environment
source env/bin/activate

# Verify Python and Django configuration
python manage.py check
```

---

## 3. Running Backend Tests

### Run All Tests (33 Automated Tests)
To execute the entire test suite across all applications:
```bash
python manage.py test
```

### Run Tests by Application
Target specific applications during development:

```bash
# Core authentication, workspace isolation & media validator tests
python manage.py test core

# Task management, board drag-and-drop & attachment security tests
python manage.py test tasks

# HTTP polling communications, DM privacy & chat upload security tests
python manage.py test communications

# AI Services, voice extraction, document RAG grounding & admin history tests
python manage.py test ai_services

# In-app notifications & read status tests
python manage.py test notifications
```

### Run a Specific Test Method
```bash
# Test video upload rejection
python manage.py test core.tests.MediaValidationTests.test_media_validation_rejects_video_files

# Test incremental polling retrieval
python manage.py test communications.tests.CommunicationsPollingAndPrivacyTests.test_incremental_polling_retrieval

# Test admin-only AI history access
python manage.py test ai_services.tests.AIOperationHistoryTests.test_ai_operation_history_admin_only_access
```

### Helpful Flags
- `--verbosity=2`: Displays verbose output with individual test names.
- `--keepdb`: Preserves the test database between runs for fast execution.
- `--failfast`: Stops execution on the first failure.

```bash
python manage.py test --verbosity=2 --keepdb
```

---

## 4. Test Suite Coverage Details

### 4.1. Core Application (`core/tests.py`)
Tests authentication, user registration, JWT generation, multi-tenant workspace isolation, and global media file validators.

| Test Class & Method | Description |
|---------------------|-------------|
| `CoreAuthAndWorkspaceTests.test_register_creates_user_and_workspace` | Tests user registration via `/api/auth/register/`. Verifies user creation, bcrypt password hashing, default workspace creation, admin member assignment, and JWT access/refresh token generation. |
| `CoreAuthAndWorkspaceTests.test_login_flow` | Verifies `/api/auth/login/` validates credentials and returns user details alongside valid JWT tokens. |
| `CoreAuthAndWorkspaceTests.test_workspace_isolation_and_unauthorized_access` | Verifies multi-tenant isolation. When User 1 attempts to query Workspace 2 with `X-Workspace-ID`, the API returns `HTTP 403 Forbidden`. |
| `MediaValidationTests.test_media_file_size_validation_rejects_over_5mb` | Verifies that files larger than 5MB raise a `ValidationError` (400 Bad Request). |
| `MediaValidationTests.test_media_validation_rejects_video_files` | Verifies that video MIME types (`video/mp4`, `video/webm`, `video/quicktime`) and extensions (`.mp4`, `.mov`, `.avi`, `.mkv`) are strictly rejected. |
| `MediaValidationTests.test_audio_duration_validation_rejects_over_60s` | Verifies that audio files exceeding 60 seconds duration are strictly rejected. |

### 4.2. Tasks Application (`tasks/tests.py`)
Tests task creation, assignment, workflow column transitions, drag-and-drop board state, and attachment validation.

| Test Method | Description |
|-------------|-------------|
| `test_create_and_assign_task` | Verifies creating a task via `/api/tasks/` with priority, description, status (`inbox`), and assignment to a `WorkspaceMember`. Verifies automatic creation of `TaskActivity` audit records. |
| `test_task_move_drag_and_drop` | Tests the drag-and-drop reordering endpoint `/api/tasks/{id}/move/`. Verifies updating status (e.g. `todo` to `in_progress`), assignee, and position column order, ensuring `TaskActivity` logs the transition. |
| `test_task_attachment_upload_rejects_video` | Verifies that attempting to upload a video attachment to a task returns `HTTP 400 Bad Request`. |
| `test_task_attachment_upload_rejects_over_5mb` | Verifies that task attachments exceeding 5MB are rejected with `HTTP 400 Bad Request`. |
| `test_task_attachment_upload_allows_valid_files` | Verifies that valid documents and images under 5MB upload successfully. |

### 4.3. Communications Application (`communications/tests.py`)
Tests the 2-second HTTP polling architecture, message cursor pagination, direct message (DM) privacy, and chat media upload restrictions.

| Test Method | Description |
|-------------|-------------|
| `test_incremental_polling_retrieval` | Validates the incremental HTTP polling contract. Ensures querying `/messages/` with `after_id=<latest>` returns 0 results when no new messages exist, and immediately returns only newly appended messages when new activity occurs. |
| `test_older_history_pagination` | Tests paginating backwards in message history using `before_id` and `limit` cursors. |
| `test_private_dm_access_control` | Verifies strict privacy controls on Direct Messages. Non-member users attempting to fetch or poll messages receive `HTTP 403 Forbidden`. |
| `test_chat_file_upload_rejects_video` | Verifies that video files uploaded to chat messages are rejected with `HTTP 400 Bad Request`. |
| `test_chat_file_upload_rejects_over_5mb` | Verifies that files larger than 5MB in chat uploads are rejected. |
| `test_chat_audio_upload_rejects_over_5mb` | Verifies that voice notes larger than 5MB in chat messages are rejected. |

### 4.4. AI Services Application (`ai_services/tests.py`)
Tests voice task extraction, entity attribution, task committing, document analysis with RAG grounding, media upload restrictions, and admin-only AI operations history.

| Test Method | Description |
|-------------|-------------|
| `test_voice_task_extraction_attribution_and_member_matching` | Tests `VoiceExtractionService.extract_structured_tasks`. Verifies unstructured transcripts are parsed into tasks, decisions, and blockers, matching member names to real workspace member IDs with evidence quotes. |
| `test_commit_extracted_tasks_endpoint` | Tests `/api/ai/tasks/commit-extracted/`. Converts AI structured suggestions into persisted `Task` records in the database. |
| `test_team_memory_rag_indexing_and_answering` | Tests `TeamMemoryRAGService`. Indexes decision documents into memory with vector embeddings and queries the knowledge base to return an answer with citations. |
| `test_voice_extraction_rejects_over_60s_audio` | Verifies that audio files longer than 60 seconds are rejected by the extraction API with a descriptive error. |
| `test_voice_extraction_rejects_over_5mb` | Verifies that audio files exceeding 5MB are rejected by the voice extraction API. |
| `test_voice_extraction_rejects_video` | Verifies that video uploads to the voice endpoint are strictly blocked. |
| `test_document_analysis_indexes_into_team_memory` | Verifies that document analyses are automatically chunked and indexed into `TeamMemoryChunk` for subsequent RAG queries. |
| `test_document_analysis_rejects_video` | Verifies that video uploads to document analysis are rejected. |
| `test_document_analysis_rejects_over_5mb` | Verifies that documents exceeding 5MB are rejected. |
| `test_ai_operation_history_admin_only_access` | Verifies that regular workspace members receive `HTTP 403 Forbidden` on `/api/ai/history/`, while workspace admins receive `HTTP 200 OK` with full operation details. |
| `test_ai_operation_history_workspace_isolation` | Verifies that AI history records cannot be accessed across different workspaces. |

### 4.5. Notifications Application (`notifications/tests.py`)
Tests in-app notifications and read state tracking.

| Test Method | Description |
|-------------|-------------|
| `test_list_notifications_and_unread_count` | Tests `/api/notifications/` returns user notifications scoped to the current workspace along with the accurate `unread_count`. |
| `test_mark_single_notification_read` | Tests `/api/notifications/{id}/read/` sets `is_read=True` on a single notification. |
| `test_mark_all_notifications_read` | Tests `/api/notifications/mark-all-read/` marks all unread notifications for the authenticated user as read. |

---

## 5. AI Model Configuration in Tests

The platform is configured to use **`gemini-3.1-flash-lite`** across all operations:
- Defined in `.env`: `GEMINI_MODEL_ID=gemini-3.1-flash-lite`
- Fallback in `plate/settings.py`: `GEMINI_MODEL_ID = env("GEMINI_MODEL_ID", default="gemini-3.1-flash-lite")`

### Graceful Fallback Mode
When running in testing or CI environments without a live Google GenAI API key:
- **Audio & Text Extraction**: Falls back to rule-based heuristics that parse action items, assignees, blockers, and decisions.
- **Vector Embeddings**: Falls back to an internal deterministic 64-dimensional L2-normalized hashing vector, ensuring RAG tests pass reliably without network access.
