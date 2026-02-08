# Codebase Audit Report

## 1. Critical Bugs (will cause crashes or data loss)

*   **File**: `gemini/datasource.py`
    *   **Description**: `SQLiteDataSource` creates a connection with default threading checks enabled (implicit) but is used in a multi-threaded context (FastAPI/Uvicorn with thread workers).
    *   **Why it’s dangerous**: Accessing the same SQLite connection from multiple threads will raise `sqlite3.ProgrammingError`, causing API 500 errors and potential transaction interruptions.

*   **File**: `gemini/agent_loops.py`
    *   **Description**: `Investigator.execute_plan` iterates through steps and stops execution immediately upon any unhandled exception, discarding partial evidence.
    *   **Why it’s dangerous**: If a single tool fails (e.g., transient network issue), the entire investigation is aborted without reporting partial success, leading to missed incidents.

*   **File**: `gemini/observer.py`
    *   **Description**: `get_system_state(simulate_failure=True)` modifies the `system_state` object in-place.
    *   **Why it’s dangerous**: The simulation logic corrupts the actual data payload. If this object is referenced elsewhere or cached, the system will hallucinate failures in subsequent legitimate checks.

## 2. Logical Bugs (behavior deviates from intent)

*   **File**: `gemini/agent_loops.py` (Verifier class)
    *   **Description**: `verify_incident` relies on hardcoded string matching (e.g., `if "source_id" in git_diff`).
    *   **Example Scenario**: A legitimate schema change that uses a different variable name (e.g., `sourceId` vs `source_id`) will fail verification despite being semantically identical, leading to false negatives.

*   **File**: `gemini/datasource.py`
    *   **Description**: Freshness calculation relies on a hardcoded dictionary map `ts_column_map`.
    *   **Example Scenario**: Adding a new table to the system will result in `freshness_minutes = 0` (always fresh), failing to detect stale data for any new tables.

## 3. Incomplete / Placeholder Implementations

*   **File**: `gemini/datasource.py`
    *   **Missing**: `get_recent_commits` returns a static list of dicts.
    *   **Risk**: The system is blind to actual code changes, rendering the "Causal Reasoning" feature useless in a real environment.

*   **File**: `gemini/agent_loops.py`
    *   **Missing**: `_tool_check_git_diff`, `_tool_verify_etl_mapping`, `_tool_monitor_baseline` are all mocks returning static strings.
    *   **Risk**: The system cannot interact with the real environment. It is currently a demo shell.

## 4. Architecture Smells

*   **Description**: **Fake AI/Agentic Behavior**. The system claims to use Gemini 3, but the `Verifier` uses rigid `if/else` statements checking for specific hardcoded substrings.
*   **Affected Files**: `agent_loops.py` (logic), `reasoner.py` (mock inference).
*   **Long-term Impact**: The "agentic" nature is an illusion. Any variation in input data breaking the hardcoded strings will cause system failure. It requires a rewrite to actually use LLM for verification.

*   **Description**: **Global Mutable State**. `api.py` uses a global `app_state` dictionary.
*   **Affected Files**: `api.py`.
*   **Long-term Impact**: In a production environment with multiple workers (gunicorn), this state will be split/inconsistent, breaking cycle tracking and websocket broadcasting.

## 5. State Management Issues

*   **Duplicated State**: `Observer` keeps a `datasource` instance but `api.py` might initialize its own ecosystem.
*   **Stale Cache Risks**: `SQLiteDataSource` keeps a persistent connection open indefinitely (`self.conn`). In a long-running app, this can lead to stale reads or database locks if the file is replaced/rotated.

## 6. Performance Risks

*   **Heuristic / Heavy Queries**: `DataSource.get_table_metrics`
    *   **Issue**: Executes `SELECT COUNT(*)` for *every single column* in a table to calculate null rates.
    *   **Impact**: On a table with 50 columns and 1M rows, this triggers 52 full table scans per cycle. This will paralyze the database.

*   **Blocking Calls**: `api.py`
    *   **Issue**: `async` endpoints call synchronous orchestrator methods.
    *   **Impact**: `get_metrics` calls `system.get_metrics_summary` (sync) inside an `async def`. If the lock or DB is busy, it blocks the event loop, causing timeouts for all users.

## 7. Core Loop Risks

*   **Weakness**: The "Smart Trigger" logic in `main.py` is hardcoded (`avg_attribution_null_rate * 5`). It does not adapt to standard deviation or statistical noise, leading to alert fatigue or missed alerts.

## 8. Suggested Implementation Roadmap

### Phase 1: Stability (Must-Fix)
1.  **Thread Safety**: Fix `SQLiteDataSource` to use thread-local connections or connection pooling.
2.  **Performance**: Optimize `get_table_metrics` to calculate all null counts in a single pass (`SELECT COUNT(col1), COUNT(col2)...`).
3.  **Global State**: Move `app_state` into a proper singleton service or Redis/DB backed store.
4.  **Error Handling**: Wrap `Investigator` steps in individual try/catch blocks to ensure partial results are returned.

### Phase 2: Reality (Remove Mocks)
1.  **Git Integration**: Replace `get_recent_commits` and `check_git_diff` with `GitPython` hooked to a real repo.
2.  **Real Verification**: Replace rigid string matching in `Verifier` with a structured LLM prompt that asks Gemini to compare the *semantic* meaning of the evidence.

### Phase 3: Scalability
1.  **Async/Await**: Refactor `Datasource` and `PerceptixSystem` to be fully async to prevent blocking the API event loop.
2.  **Dynamic Configuration**: Move hardcoded thresholds (freshness 1440 mins, null rate 0.05) to a config file or database table.
