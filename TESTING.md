# Plate Backend Testing Documentation

This document describes the test suite architecture, coverage, execution methods, and testing patterns for the Plate Backend API.

---

## 1. Test Architecture Overview

The Plate backend test suite is built with the native **Django Test Framework** (`django.test.TestCase`) and **Django REST Framework Test Client** (`rest_framework.test.APIClient`).

### Key Testing Principles
- **Database Isolation**: Each test runs inside an isolated database transaction that rolls back automatically upon completion.
- **Multi-Tenant Workspace Security**: All endpoints enforce header-based tenant isolation via `X-Workspace-ID`. Tests verify cross-tenant access denial (`HTTP 403 Forbidden`).
- **Resilient AI Mocking & Fallbacks**: The AI services are designed with deterministic rule-based and vector fallbacks. Tests run reliably in CI and offline environments without external network dependencies.
- **Authentication**: JWT token authentication and `APIClient.force_authenticate(user)` are used to simulate authenticated user workflows.

---

## 2. Environment Activation

Before running tests, ensure your virtual environment is activated from the root `plate-backend` folder:

```bash
# Activate the environment (both env and venv paths are supported)
source env/bin/activate

# Verify Python and Django configuration
python manage.py check
```

---

## 3. Running Backend Tests

### Run All Tests
To execute the entire test suite across all applications:
```bash
python manage.py test
```

### Run Tests by App
You can target specific applications to speed up test execution during development:

```bash
# Core authentication & workspace tests
python manage.py test core

# Task management & board drag-and-drop tests
python manage.py test tasks

# HTTP polling communications & DM privacy tests
python manage.py test communications

# AI Services, Voice task extraction, and RAG Team Memory tests
python manage.py test ai_services

# In-app notifications & read status tests
python manage.py test notifications
```

### Run a Specific Test Case or Method
```bash
# Run a specific test class
python manage.py test core.tests.CoreAuthAndWorkspaceTests

# Run a single test method
python manage.py test communications.tests.CommunicationsPollingAndPrivacyTests.test_incremental_polling_retrieval
```

### Helpful Flags
- `--verbosity=2`: Displays verbose output with individual test names.
- `--keepdb`: Preserves the test database between runs for significantly faster execution.
- `--failfast`: Stops execution on the first failure.

```bash
python manage.py test --verbosity=2 --keepdb
```

---

## 4. Test Suite Details

### 4.1. Core Application (`core/tests.py`)
Tests authentication, user registration, JWT generation, and multi-tenant workspace isolation.

| Test Method | Description |
|-------------|-------------|
| `test_register_creates_user_and_workspace` | Tests user registration via `/api/auth/register/`. Verifies user creation, bcrypt password hashing, automatic default workspace creation, admin member assignment, and JWT access/refresh token generation. |
| `test_login_flow` | Verifies `/api/auth/login/` validates credentials and returns user details alongside valid JWT tokens. |
| `test_workspace_isolation_and_unauthorized_access` | Verifies multi-tenant isolation. When User 1 attempts to query Workspace 2 with `X-Workspace-ID`, the API returns `HTTP 403 Forbidden`. |

### 4.2. Tasks Application (`tasks/tests.py`)
Tests task creation, assignment, workflow column transitions, and drag-and-drop board state.

| Test Method | Description |
|-------------|-------------|
| `test_create_and_assign_task` | Verifies creating a task via `/api/tasks/` with priority, description, status (`inbox`), and assignment to a `WorkspaceMember`. Verifies automatic creation of `TaskActivity` audit records. |
| `test_task_move_drag_and_drop` | Tests the drag-and-drop reordering endpoint `/api/tasks/{id}/move/`. Verifies updating status (e.g. `todo` to `in_progress`), assignee, and position column order, ensuring `TaskActivity` logs the transition. |

### 4.3. Communications Application (`communications/tests.py`)
Tests the 2-second HTTP polling architecture, message cursor pagination, and direct message (DM) privacy.

| Test Method | Description |
|-------------|-------------|
| `test_incremental_polling_retrieval` | Validates the incremental HTTP polling contract. Ensures querying `/messages/` with `after_id=<latest>` returns 0 results when no new messages exist, and immediately returns only newly appended messages when new activity occurs. |
| `test_older_history_pagination` | Tests paginating backwards in message history using `before_id` and `limit` cursors. |
| `test_private_dm_access_control` | Verifies strict privacy controls on Direct Messages. Non-member users attempting to fetch or poll messages receive `HTTP 403 Forbidden`. |

### 4.4. AI Services Application (`ai_services/tests.py`)
Tests voice task extraction, entity attribution, task committing, and Team Memory (RAG) vector querying using `gemini-3.1-flash-lite`.

| Test Method | Description |
|-------------|-------------|
| `test_voice_task_extraction_attribution_and_member_matching` | Tests `VoiceExtractionService.extract_structured_tasks`. Verifies unstructured transcripts are parsed into tasks, decisions, and blockers, matching member names (e.g. "Dave") to real workspace member IDs with evidence quotes. |
| `test_commit_extracted_tasks_endpoint` | Tests `/api/ai/tasks/commit-extracted/`. Converts AI structured suggestions into persisted `Task` records in the database. |
| `test_team_memory_rag_indexing_and_answering` | Tests `TeamMemoryRAGService`. Indexes decision documents into memory with vector embeddings and queries the knowledge base to return an answer with citations. |

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
