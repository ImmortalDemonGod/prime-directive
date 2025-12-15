# Comprehensive Code Audit: Prime Directive Repository

**Document ID:** `CODE-AUDIT-V1.0-PRIME-DIRECTIVE`  
**Date:** 2025-12-14  
**Auditor Role:** Senior Systems Architect & Code Quality Analyst  
**Repository:** `prime-directive` (Python-based CLI orchestration system)

---

## Executive Summary: Aspiration vs. Implementation Reality

### The Vision
Prime Directive aspires to be a **"Meta-Orchestration Layer"** for managing multi-project contexts—a sophisticated system to eliminate context-switching friction through:
- Automatic state preservation (Git + Terminal + Tasks)
- AI-powered situation reports (SITREPs)
- Seamless tmux/editor integration
- Cross-domain synergy tracking

### The Reality
The codebase reveals a **well-architected foundation with critical integration gaps**. The individual components (Git utils, DB schema, Terminal capture) are professionally implemented with strong engineering discipline. However, the promised "holistic integration" exists primarily in documentation rather than executable code.

**Key Finding:** This is a **60% complete MVP**. The plumbing is excellent; the integration layer is nascent.

---

## 1. Codebase Overview & Architecture Analysis

### 1.1 Directory Structure Assessment

```
prime-directive/
├── prime_directive/          # Core application code
│   ├── bin/                 # CLI entry points (pd.py, pd_daemon.py)
│   ├── core/                # Business logic modules
│   │   ├── config.py       # Hydra-based configuration
│   │   ├── db.py           # SQLModel async DB layer
│   │   ├── git_utils.py    # Git state capture
│   │   ├── scribe.py       # AI SITREP generation
│   │   ├── tasks.py        # TaskMaster integration
│   │   ├── terminal.py     # Terminal state capture
│   │   ├── tmux.py         # Session management
│   │   └── windsurf.py     # Editor control
│   ├── system/             # Configuration & shell integration
│   └── conf/               # Hydra config files
├── tests/                  # Comprehensive test suite
└── data/                   # SQLite DB & logs (gitignored)
```

**Analysis:** 
- ✅ Clean separation of concerns (bin/core/system)
- ✅ Test coverage exists for all major modules
- ⚠️ The `conf/` directory uses Hydra, but the `system/` directory duplicates config in YAML
- ❌ **Critical Gap:** No `integration/` or `orchestrator/` module that ties the pieces together

---

### 1.2 Technology Stack Validation

| Component | Technology | Status | Assessment |
|-----------|-----------|--------|------------|
| **CLI Framework** | Typer 0.20.0 | ✅ Mature | Excellent choice for rich CLI apps |
| **Database** | SQLModel + aiosqlite | ✅ Functional | Async SQLite is appropriate for N=1 use case |
| **Config Management** | Hydra + OmegaConf | ⚠️ Partially Used | Over-engineered for current complexity |
| **AI Integration** | Ollama (HTTP API) | ⚠️ Brittle | No retry logic, hardcoded localhost |
| **Session Manager** | tmux (subprocess) | ✅ Solid | Proper timeout handling |
| **Editor Control** | Windsurf CLI | ⚠️ Untested | Assumes `windsurf -n` works like VS Code |

**Critical Findings:**
1. **Hydra Overkill:** The project uses both Hydra structured configs AND manual YAML parsing (`registry.py`). This is architectural confusion.
2. **No Ollama Health Checks:** The `scribe.py` module will fail silently if Ollama is down.
3. **Mock Mode Everywhere:** The extensive use of `mock_mode` flags suggests the system hasn't been battle-tested in production.

---

## 2. Module-by-Module Deep Dive

### 2.1 `core/config.py` — Configuration Management

**Stated Purpose:** Provide Hydra-based structured configuration.

**Actual Behavior:**
```python
@dataclass
class SystemConfig:
    editor_cmd: str = "windsurf"
    ai_model: str = "qwen2.5-coder"
    db_path: str = "data/prime.db"
    log_path: str = "data/logs/pd.log"
    mock_mode: bool = False  # ⚠️ This is a code smell
```

**Critical Issues:**
1. **Dead Code:** This dataclass is defined but never imported or used in `bin/pd.py`. The actual config loading happens via `load_config()` which reads `conf/config.yaml` directly.
2. **Redundant Systems:** The project has THREE config systems:
   - Hydra dataclasses (`config.py`)
   - Manual YAML parsing (`registry.py`)
   - OmegaConf loading (`pd.py`)
3. **Mock Mode Antipattern:** Having a global `mock_mode` flag scattered across the codebase is a maintenance nightmare. Proper solution: dependency injection or a test harness.

**Recommendation:** **DELETE** `core/config.py` and unify on a single config system (prefer Hydra if you need composability, else stick with raw YAML + Pydantic).

---

### 2.2 `core/db.py` — Database Layer

**Stated Purpose:** Async SQLite persistence for Repository and ContextSnapshot.

**Actual Behavior:**
```python
class Repository(SQLModel, table=True):
    id: str = Field(primary_key=True)
    path: str
    priority: int
    active_branch: Optional[str] = None
    last_snapshot_id: Optional[int] = Field(default=None)  # ❌ Foreign key not enforced

class ContextSnapshot(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    repo_id: str = Field(index=True)  # ❌ No FK constraint
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    git_status_summary: str
    terminal_last_command: str
    terminal_output_summary: str
    ai_sitrep: str
```

**Critical Issues:**
1. **No Foreign Key Constraints:** `ContextSnapshot.repo_id` has no FK to `Repository.id`. This allows orphaned snapshots.
2. **No Relationships Defined:** SQLModel supports relationships, but they're not used. This makes querying "get latest snapshot for repo X" unnecessarily verbose.
3. **Global Engine Singleton:** The `_async_engine` global is fragile. If `init_db()` is called with different paths, the old engine is not disposed.

**Proof of Fragility:**
```python
# In pd.py, this pattern appears multiple times:
async def freeze_logic(...):
    await init_db(config.system.db_path)
    async for session in get_session(config.system.db_path):
        # ... do work ...
    await dispose_engine()  # ❌ Manually managed lifecycle
```

If an exception occurs before `dispose_engine()`, the connection pool leaks.

**Recommendation:** Use SQLModel relationships and a proper async context manager for the engine lifecycle.

---

### 2.3 `core/git_utils.py` — Git State Capture

**Stated Purpose:** Capture branch, dirty state, and diff summary.

**Actual Behavior:**
```python
def get_status(repo_path: str) -> Dict[str, Union[str, bool, List[str]]]:
    # 1. Get branch
    branch_proc = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_path, timeout=5, ...
    )
    
    # 2. Get status (porcelain)
    status_proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_path, timeout=5, ...
    )
    
    # 3. Parse uncommitted files with regex
    uncommitted_files = []
    for line in status_output.splitlines():
        match = re.match(r"^(.{2}) (.*)$", line)
        if match:
            uncommitted_files.append(match.group(2))
```

**Analysis:**
- ✅ Proper timeout handling (5 seconds)
- ✅ Comprehensive error handling (TimeoutExpired, Exception)
- ✅ Returns structured data with clear semantics
- ⚠️ **Edge Case Missed:** Renames and copies in Git show as `R  old -> new`. The current regex will fail to parse these correctly.

**Test Coverage Check:**
```python
# tests/test_git.py only tests:
# - Clean repo
# - Modified file
# - New file (untracked)
# ❌ Missing: Renamed files, submodules, detached HEAD, merge conflicts
```

**Recommendation:** Add test cases for complex Git states.

---

### 2.4 `core/scribe.py` — AI SITREP Generation

**Stated Purpose:** Generate concise situation reports using Ollama.

**Actual Behavior:**
```python
def generate_sitrep(...) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system_prompt,
        "stream": False
    }
    
    try:
        response = requests.post(api_url, json=payload, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data.get("response", "Error: No response from AI model.")
    except requests.exceptions.RequestException as e:
        return f"Error generating SITREP: {str(e)}"
```

**Critical Issues:**
1. **No Retry Logic:** If Ollama is temporarily busy, the entire freeze operation fails.
2. **Hardcoded Timeout:** 5 seconds is arbitrary. For complex repos, the AI might need 10-15 seconds.
3. **Silent Failure:** Errors are returned as strings, not raised as exceptions. This makes debugging impossible.
4. **No Prompt Engineering:** The system prompt is hardcoded. No versioning or A/B testing capability.

**Proof of Brittleness:**
From `tests/test_scribe.py`:
```python
def test_generate_sitrep_timeout():
    with patch("requests.post", side_effect=requests.exceptions.Timeout("Timed out")):
        result = generate_sitrep(...)
        assert "Error generating SITREP" in result  # ❌ This is NOT proper error handling
```

**Recommendation:** 
1. Add exponential backoff retry (using `tenacity` library)
2. Raise exceptions instead of returning error strings
3. Make timeout configurable
4. Add prompt versioning system

---

### 2.5 `core/tasks.py` — TaskMaster Integration

**Stated Purpose:** Extract active tasks from `.taskmaster/tasks.json`.

**Actual Behavior:**
```python
def get_active_task(repo_path: str) -> Optional[Dict[str, Any]]:
    tasks_path = os.path.join(repo_path, ".taskmaster", "tasks", "tasks.json")
    
    if not os.path.exists(tasks_path):
        return None
    
    # ... parse JSON ...
    
    for tag_data in data.values():
        for task in tag_data["tasks"]:
            if task.get("status") == "in-progress":
                in_progress_tasks.append((p_val, task))
    
    in_progress_tasks.sort(key=sort_key, reverse=True)
    return in_progress_tasks[0][1]
```

**Analysis:**
- ✅ Graceful handling of missing file
- ✅ Priority-based sorting
- ⚠️ **Assumption Violation:** The code assumes TaskMaster's schema (nested `master.tasks[]`). If TaskMaster changes its schema, this breaks.
- ❌ **No Schema Validation:** The code silently fails if the JSON is malformed.

**Recommendation:** Add JSON schema validation using `jsonschema` library.

---

### 2.6 `core/tmux.py` — Session Management

**Stated Purpose:** Create/attach tmux sessions idempotently.

**Actual Behavior:**
```python
def ensure_session(repo_id: str, repo_path: str):
    session_name = f"pd-{repo_id}"
    
    # Check if session exists
    result = subprocess.run(
        ["tmux", "has-session", "-t", session_name],
        capture_output=True, timeout=2
    )
    
    if result.returncode != 0:
        # Create new session
        cmd = f"cd {repo_path} && (uv shell || $SHELL)"
        subprocess.run([
            "tmux", "new-session", "-d", "-s", session_name,
            "bash", "-c", cmd
        ], timeout=5)
    
    # Attach logic
    if os.environ.get("TMUX"):
        subprocess.run(["tmux", "switch-client", "-t", session_name], timeout=2)
    else:
        subprocess.run(["tmux", "attach-session", "-t", session_name])  # ❌ No timeout!
```

**Critical Issues:**
1. **Blocking Call:** The final `attach-session` has no timeout. This hands control to tmux forever.
2. **Shell Injection Risk:** The `cmd` string is constructed with `f"{repo_path}"`. If a repo path contains shell metacharacters, this is exploitable.
3. **Environment Pollution:** The session inherits the caller's environment, which might have stale `VIRTUAL_ENV` or other variables.

**Proof of Risk:**
```python
# Malicious repo path
repo_path = "/tmp/repo; rm -rf ~"
# Becomes: cd /tmp/repo; rm -rf ~ && (uv shell || $SHELL)
```

**Recommendation:** Use `shlex.quote()` for shell escaping, or avoid shell altogether by using tmux's `-c` flag for working directory.

---

### 2.7 `bin/pd.py` — Main CLI Orchestrator

**Stated Purpose:** The user-facing CLI that orchestrates freeze/switch/status operations.

**Actual Behavior:** This is the most critical file. Let's trace the `switch` command:

```python
@app.command("switch")
def switch(repo_id: str):
    cfg = load_config()
    
    # 1. Detect current repo
    cwd = os.getcwd()
    current_repo_id = None
    for r_id, r_config in cfg.repos.items():
        if cwd.startswith(os.path.abspath(r_config.path)):
            current_repo_id = r_id
            break
    
    # 2. Freeze current repo
    if current_repo_id and current_repo_id != repo_id:
        freeze_logic(current_repo_id, cfg)
    
    # 3. Switch to target
    ensure_session(repo_id, target_repo.path)
    launch_editor(target_repo.path, cfg.system.editor_cmd)
    
    # 4. Show SITREP
    async def show_sitrep():
        # ... query DB ...
```

**Critical Issues:**

1. **Race Condition in Repo Detection:**
```python
if cwd.startswith(os.path.abspath(r_config.path)):
```
If you have nested repos (e.g., `/projects/parent/` and `/projects/parent/child/`), this will match the wrong one.

2. **Freeze is Synchronous, Thaw is Not:**
The `freeze_logic()` is called inline, blocking the CLI. But `show_sitrep()` is async and runs separately. If freeze fails, switch still proceeds.

3. **No Transaction Semantics:**
If `ensure_session()` fails after `freeze_logic()` succeeds, you've frozen the old context but failed to enter the new one. No rollback mechanism.

4. **DB Engine Not Disposed:**
```python
async def show_sitrep():
    await init_db(cfg.system.db_path)
    async for session in get_session(...):
        # ... query ...
    # ❌ Missing: await dispose_engine()
```

**Proof of Brittleness:**
From `tests/test_switch.py`:
```python
@patch("prime_directive.bin.pd.freeze_logic") 
@patch("prime_directive.bin.pd.ensure_session")
def test_switch_command(mock_ensure, mock_freeze, ...):
    result = runner.invoke(app, ["switch", "target-repo"])
    
    mock_freeze.assert_called_once()
    mock_ensure.assert_called_once()
    # ❌ Test doesn't verify what happens if mock_ensure FAILS
```

**Recommendation:** Implement proper async orchestration with transaction-like semantics (freeze/switch/thaw as atomic unit).

---

## 3. Execution Trace: The "Monday Morning Warp" Scenario

Let's simulate the flagship use case from the PRD: switching from `black-box` to `rna-predict` after a weekend.

### Input State:
- CWD: `/projects/black-box/src/`
- Target: `rna-predict`
- Last snapshot for `rna-predict`: 72 hours old

### Execution Flow:

```
1. User types: `pd switch rna-predict`
   ↓
2. load_config()
   → Reads conf/config.yaml via Hydra
   → ✅ Success: Config loaded
   ↓
3. Detect current repo
   → cwd.startswith("/projects/black-box/") → Match found
   → current_repo_id = "black-box"
   ↓
4. Call freeze_logic("black-box", cfg)
   ↓
   4a. get_status("/projects/black-box")
       → subprocess: git status --porcelain
       → ✅ Returns: {"is_dirty": True, "uncommitted_files": ["main.py"]}
   ↓
   4b. capture_terminal_state("black-box")
       → subprocess: tmux capture-pane -p -S -50 -t pd-black-box
       → ⚠️ Timeout if tmux is not running
       → Returns: ("unknown", "No tmux session found")
   ↓
   4c. get_active_task("/projects/black-box")
       → Opens .taskmaster/tasks/tasks.json
       → ✅ Returns: {"id": 42, "title": "Fix tensor bug"}
   ↓
   4d. generate_sitrep(...)
       → POST to http://localhost:11434/api/generate
       → ⚠️ Hangs if Ollama is not running
       → Timeout after 5 seconds
       → Returns: "Error generating SITREP: Connection refused"
   ↓
   4e. Save to DB
       → await init_db()
       → ✅ Creates snapshot with ERROR as sitrep
   ↓
5. Call ensure_session("rna-predict", "/projects/rna-predict")
   ↓
   5a. Check if session exists
       → subprocess: tmux has-session -t pd-rna-predict
       → Return code: 1 (doesn't exist)
   ↓
   5b. Create new session
       → subprocess: tmux new-session -d -s pd-rna-predict bash -c "cd /projects/rna-predict && (uv shell || $SHELL)"
       → ✅ Session created
   ↓
   5c. Attach to session
       → subprocess: tmux attach-session -t pd-rna-predict
       → ⚠️ This BLOCKS the Python process indefinitely
   ↓
6. launch_editor("/projects/rna-predict", "windsurf")
   → ❌ NEVER REACHED because tmux attach blocked!
   ↓
7. show_sitrep()
   → ❌ NEVER REACHED
```

### Actual Result:
- ❌ User is in a tmux session, but Windsurf did not open
- ❌ No SITREP displayed
- ❌ Previous context was saved with an ERROR sitrep
- ⚠️ If user now Ctrl-C's, the tmux session remains but the Python process crashes

**This is NOT the "Monday Morning Warp." This is a broken workflow.**

---

## 4. Critical Findings & Risk Assessment

### 4.1 Logical Flaws

| Issue | Severity | Impact | Evidence |
|-------|----------|--------|----------|
| **Blocking tmux attach** | 🔴 Critical | Entire workflow hangs | `tmux.py:55` |
| **No retry logic in Ollama** | 🔴 Critical | Freeze fails if AI down | `scribe.py:42` |
| **Foreign key violations possible** | 🟠 High | Data integrity at risk | `db.py:15` |
| **Shell injection in tmux** | 🟠 High | Security vulnerability | `tmux.py:32` |
| **Race condition in repo detection** | 🟡 Medium | Wrong repo detected | `pd.py:152` |
| **No transaction semantics** | 🟡 Medium | Partial freeze/switch | `pd.py:175` |

### 4.2 Performance Bottlenecks

1. **Serial Git Operations:** The `get_status()` function runs 3 sequential subprocess calls. These could be parallelized using `asyncio.gather()`.

2. **Unoptimized DB Queries:** The `show_sitrep()` function does:
```python
stmt = select(ContextSnapshot).where(...).order_by(...).limit(1)
```
Without an index on `(repo_id, timestamp)`, this is a table scan.

3. **No Connection Pooling:** Each operation creates a new DB engine. For rapid freeze/switch cycles, this is inefficient.

### 4.3 Structural/Architectural Weaknesses

1. **Tight Coupling:** The `freeze_logic()` function directly calls `get_status()`, `capture_terminal_state()`, `get_active_task()`, and `generate_sitrep()`. If any one fails, the entire freeze fails. No fault tolerance.

2. **Missing Orchestration Layer:** There's no `core/orchestrator.py` or `core/coordinator.py` that manages the state machine of freeze → switch → thaw. The logic is scattered across `pd.py`.

3. **God Function:** The `freeze_logic()` function is 50+ lines and does 5 different things. This violates Single Responsibility Principle.

4. **No Circuit Breaker:** If Ollama is down, the system should degrade gracefully (e.g., save snapshot without SITREP). Currently, it fails loudly.

---

## 5. Recommendations & Redesign Proposals

### 5.1 Immediate Fixes (P0 - Must Fix Before Use)

1. **Fix tmux attach blocking:**
```python
# In tmux.py
def ensure_session(repo_id: str, repo_path: str):
    # ... existing code ...
    
    # Instead of blocking attach:
    if os.environ.get("TMUX"):
        subprocess.run(["tmux", "switch-client", "-t", session_name], timeout=2)
    else:
        # Use detached execution + exec replacement
        os.execvp("tmux", ["tmux", "attach-session", "-t", session_name])
```

2. **Add retry logic to Ollama:**
```python
# In scribe.py
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def generate_sitrep(...) -> str:
    # ... existing code ...
```

3. **Add DB foreign keys:**
```python
# In db.py
class ContextSnapshot(SQLModel, table=True):
    repo_id: str = Field(foreign_key="repository.id", index=True)
```

### 5.2 Architectural Refactoring (P1 - Critical for Robustness)

1. **Introduce an Orchestrator:**
```python
# New file: core/orchestrator.py
class ContextSwitchOrchestrator:
    async def freeze(self, repo_id: str) -> FreezeResult:
        """Atomic freeze operation with rollback on failure."""
        
    async def switch(self, from_repo: str, to_repo: str) -> SwitchResult:
        """Coordinated freeze + thaw with transaction semantics."""
        
    async def thaw(self, repo_id: str) -> ThawResult:
        """Restore context from latest snapshot."""
```

2. **Implement Circuit Breaker for External Services:**
```python
# core/circuit_breaker.py
class OllamaCircuitBreaker:
    def __init__(self, failure_threshold=3, timeout=30):
        self.failures = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
            else:
                raise CircuitBreakerOpen("Ollama service unavailable")
        
        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failures = 0
            return result
        except Exception as e:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.state = "OPEN"
                self.last_failure_time = time.time()
            raise
```

3. **Unify Configuration:**
```python
# Delete core/config.py
# Consolidate to single system:
# - Use Hydra if you need composability
# - Use Pydantic if you need validation
# - Pick ONE and delete the other
```

### 5.3 Testing Gaps to Fill (P2)

1. **Integration Tests:** The current tests are all unit tests. Add:
   - `tests/integration/test_freeze_switch_e2e.py`
   - `tests/integration/test_tmux_session_lifecycle.py`

2. **Chaos Engineering Tests:**
```python
# tests/chaos/test_ollama_failure.py
@pytest.mark.chaos
def test_freeze_with_ollama_down():
    """Verify system degrades gracefully when AI is unavailable."""
    with mock_ollama_connection_refused():
        result = freeze_logic("test-repo", config)
        # Should succeed with partial data
        assert result.snapshot_id is not None
        assert "Error" in result.sitrep
```

3. **Property-Based Tests:**
```python
# tests/property/test_git_parsing.py
from hypothesis import given, strategies as st

@given(st.text(min_size=1))
def test_git_status_parsing_never_crashes(git_output):
    """Verify parser handles arbitrary git output without crashing."""
    # Should either parse successfully or raise specific exception
```

---

## 6. Conclusion: The Path to Production Readiness

### Current State: **60% Complete MVP**

**What Works:**
- ✅ Clean architecture and separation of concerns
- ✅ Comprehensive error handling in individual modules
- ✅ Strong test coverage for unit logic
- ✅ Excellent documentation (PRD, technical specs)

**What's Broken:**
- ❌ The core workflow (freeze → switch → thaw) is not end-to-end functional
- ❌ Critical blocking bug in tmux session management
- ❌ No fault tolerance for external dependencies (Ollama, tmux)
- ❌ Missing integration layer to tie components together

### Roadmap to Production:

**Phase 1: Make It Work (1-2 weeks)**
1. Fix the tmux attach blocking bug
2. Add circuit breaker for Ollama
3. Write one E2E integration test
4. Manually test the "Monday Morning Warp" scenario

**Phase 2: Make It Right (2-3 weeks)**
1. Implement the Orchestrator pattern
2. Add DB foreign key constraints
3. Unify configuration system
4. Add comprehensive integration tests

**Phase 3: Make It Fast (1 week)**
1. Add DB indexes
2. Parallelize Git operations
3. Implement connection pooling

**Phase 4: Make It Resilient (2 weeks)**
1. Add graceful degradation
2. Implement rollback mechanisms
3. Add chaos engineering tests
4. Deploy to production with real repos

### Final Verdict:

This codebase demonstrates **exceptional engineering discipline** at the module level, but **insufficient integration testing** at the system level. The individual components are production-ready; the system as a whole is not.

**The core promise of Prime Directive—seamless, AI-powered context switching—is achievable, but requires 4-6 weeks of focused integration work before it can be trusted for daily use.**

The architecture is sound. The execution is 60% there. **This is fixable, not fundamental.**