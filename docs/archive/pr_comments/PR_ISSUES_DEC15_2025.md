**Actionable comments posted: 8**

<details>
<summary>♻️ Duplicate comments (5)</summary><blockquote>

<details>
<summary>prime_directive/core/terminal.py (1)</summary><blockquote>

`4-56`: ** Address API inconsistencies flagged in previous review.**

Previous review correctly identified two issues that remain unresolved:

1. **API/docstring mismatch**: Docstring (line 14) promises "last command executed (if available)" but implementation (line 46) always returns `"unknown"` placeholder. Either implement basic command extraction or update the docstring to explicitly document the placeholder behavior.

2. **Inconsistent error sentinel**: Lines 55-56 catch `OSError` and return `("error", str(e))`, which diverges from the `"unknown"` convention used in all other exception handlers (lines 50-51, 52-54) and leaks raw exception messages. For API stability:

```diff
-    except OSError as e:
-        return "error", str(e)
+    except OSError:
+        return "unknown", "Unexpected error during terminal capture."
```

</blockquote></details>
<details>
<summary>prime_directive/core/dependencies.py (1)</summary><blockquote>

`42-57`: ** Substring model matching causes false positives.**

As identified in the previous review, line 53 uses substring matching:

```python
return any(model_name in name for name in model_names)
```

This causes false positives where searching for `"llama"` would match `"codellama:7b"`. Use exact or prefix matching instead:

```diff
-        return any(model_name in name for name in model_names)
+        # Match exact name or name with tag (e.g., "qwen2.5-coder" matches "qwen2.5-coder:latest")
+        return any(name == model_name or name.startswith(f"{model_name}:") for name in model_names)
```

</blockquote></details>
<details>
<summary>prime_directive/core/ai_providers.py (1)</summary><blockquote>

`7-25`: **Inconsistent error handling pattern persists.**

This was flagged in a previous review: `generate_ollama` raises exceptions for HTTP errors via `raise_for_status()` but returns an error string when the `"response"` field is missing. Callers must handle both exceptions and error strings differently.

</blockquote></details>
<details>
<summary>prime_directive/bin/pd.py (1)</summary><blockquote>

`3-3`: **Unused import: `requests`.**

This was flagged in a previous review.

</blockquote></details>
<details>
<summary>prime_directive/core/scribe.py (1)</summary><blockquote>

`71-92`: **Deduplicate Ollama HTTP/retry logic by reusing `generate_ollama` from `ai_providers`.**

This block reimplements payload construction, HTTP POST, and retry/backoff that are already encapsulated in `generate_ollama` in `prime_directive.core.ai_providers`. Reusing that helper would keep behavior consistent across the codebase and avoid drift if the Ollama integration changes (e.g., new fields, error-handling). The existing `last_error` pattern can wrap the helper call so your fallback behavior stays the same.




```diff
-from prime_directive.core.ai_providers import generate_openai_chat, get_openai_api_key
+from prime_directive.core.ai_providers import (
+    generate_ollama,
+    generate_openai_chat,
+    get_openai_api_key,
+)
@@
-    payload = {
-        "model": model,
-        "prompt": prompt,
-        "system": system_prompt,
-        "stream": False
-    }
-
-    last_error: Optional[Exception] = None
-    attempts = max_retries + 1
-    for attempt in range(attempts):
-        try:
-            response = requests.post(api_url, json=payload, timeout=timeout_seconds)
-            response.raise_for_status()
-            data = response.json()
-            return data.get("response", "Error: No response from AI model.")
-        except requests.exceptions.RequestException as e:
-            last_error = e
-            if attempt >= attempts - 1:
-                break
-            if backoff_seconds > 0:
-                time.sleep(backoff_seconds * (2 ** attempt))
+    last_error: Optional[Exception] = None
+    try:
+        # Delegate Ollama interaction (including retries/backoff) to shared helper.
+        return generate_ollama(
+            api_url=api_url,
+            model=model,
+            prompt=prompt,
+            system=system_prompt,
+            # Pass through timeout/retry/backoff options as supported by generate_ollama.
+            timeout_seconds=timeout_seconds,
+            # e.g. max_retries=max_retries, backoff_seconds=backoff_seconds
+        )
+    except requests.exceptions.RequestException as e:
+        last_error = e
```

(Adjust keyword arguments to match the actual `generate_ollama` signature.)

</blockquote></details>

</blockquote></details>

<details>
<summary>🧹 Nitpick comments (22)</summary><blockquote>

<details>
<summary>.github/ISSUE_TEMPLATE/feature_request.md (1)</summary><blockquote>

`10-26`: **Clear structure with guided prompts—consider providing a concrete example command.**

The restructured sections (Problem or Use Case → Proposed Solution → Example Usage → Alternatives Considered) follow a logical workflow and help reporters provide complete context. However, the bash example uses a generic placeholder (`pd new-command --option value`). 

If the project's CLI has common operations (e.g., `pd context switch`, `pd freeze context`), providing a more realistic example would better guide users and reduce friction when opening feature requests.

</blockquote></details>
<details>
<summary>mkdocs.yml (1)</summary><blockquote>

`6-7`: **Verify referenced documentation files exist and consider decoupling date from audit filename.**

The nav configuration references two documentation files. Please confirm both `docs/index.md` and `docs/CODE-AUDIT-V1.0-PRIME-DIRECTIVE_2025-12-14_01.md` exist at the expected paths.

Additionally, the date hardcoded in the audit filename (`2025-12-14`) creates a maintenance coupling—if the document is updated later, the filename will become stale. Consider using a versioning scheme (e.g., `CODE-AUDIT-V1.0.md`) or dynamically linking to the latest audit without the date in the filename.

</blockquote></details>
<details>
<summary>.github/workflows/main.yml (2)</summary><blockquote>

`17-32`: **Consider adding Python 3.12 to the linter job.**

The linter job only runs on Python 3.11, but the tests matrix includes 3.12. Any linting issues specific to Python 3.12 will only be caught during test execution, which is less efficient.

Apply this diff to add Python 3.12 to the linter matrix:

```diff
  linter:
    strategy:
      fail-fast: false
      matrix:
-       python-version: ["3.11"]
+       python-version: ["3.11", "3.12"]
        os: [ubuntu-latest]
```

---

`87-90`: **Unify installation method across all platforms.**

The Windows test job uses `pip install -e .[test]` directly, while Linux and macOS use `make install`. For consistency and reproducibility, all platforms should use the same installation approach.

Apply this diff to align the Windows install with other platforms:

```diff
      - name: Install Pip
        run: pip install --user --upgrade pip
      - name: Install project
-       run: pip install -e .[test]
+       run: make install
      - name: run tests
```

Alternatively, if `make` isn't available on Windows, consider using `pip install -e .[test]` across all platforms for simplicity.

</blockquote></details>
<details>
<summary>prime_directive/core/windsurf.py (1)</summary><blockquote>

`14-17`: **Consider early return when editor command is not found.**

The function prints a warning when the editor command is not found but continues execution. Since `subprocess.Popen` requires an executable in PATH, continuing will inevitably raise `FileNotFoundError` on Line 23. Consider returning early or raising a more informative exception.



Apply this diff to return early:

```diff
     # Verify editor command exists
     if not shutil.which(editor_cmd):
-        print(f"Warning: Editor command '{editor_cmd}' not found in PATH.")
-        # We try to run it anyway in case it's an alias or shell function, 
-        # but subprocess.Popen usually needs an executable in PATH.
+        print(f"Error: Editor command '{editor_cmd}' not found in PATH.")
+        return
```

</blockquote></details>
<details>
<summary>prime_directive/core/logging_utils.py (1)</summary><blockquote>

`3-3`: **Remove unused import.**

The `yaml` module is imported but never used in this file.



Apply this diff:

```diff
 import logging
 import logging.config
-import yaml
 import os
```

</blockquote></details>
<details>
<summary>prime_directive/core/tasks.py (1)</summary><blockquote>

`56-69`: **Consider documenting tie-breaking behavior for non-numeric task IDs.**

When task IDs are non-numeric (or missing), they're treated as `0` for sorting purposes. If multiple in-progress tasks have the same priority and non-numeric IDs, the selection order becomes arbitrary. This is likely acceptable, but documenting this edge case would improve maintainability.



Consider adding a comment above the sort_key function:

```diff
+    # Sort by priority (desc) then by task ID (desc).
+    # Non-numeric IDs are treated as 0 for sorting.
+    # If multiple tasks have the same priority and non-numeric IDs, order is arbitrary.
     def sort_key(item):
```

</blockquote></details>
<details>
<summary>tests/test_freeze.py (1)</summary><blockquote>

`35-85`: **Comprehensive test coverage with one unused mock.**

The test thoroughly validates the freeze command workflow, including console output, DB interactions, and snapshot field values. The async session mocking is properly structured.



However, the `mock_init_db` parameter (line 42) is patched but never referenced in the test body. Consider removing it if init_db calls are not expected to be verified:

```diff
-@patch("prime_directive.bin.pd.init_db", new_callable=AsyncMock)
 @patch("prime_directive.bin.pd.get_session")
-def test_freeze_command(mock_get_session, mock_init_db, mock_generate_sitrep, ...):
+def test_freeze_command(mock_get_session, mock_generate_sitrep, ...):
```

</blockquote></details>
<details>
<summary>tests/test_cli.py (1)</summary><blockquote>

`47-95`: **Solid status command test with one unused mock.**

The test properly validates status output, DB queries, and cleanup with well-structured async session mocking.



However, the `mock_init_db` parameter (line 52) is patched but never used in the test. Consider removing it:

```diff
-@patch("prime_directive.bin.pd.init_db", new_callable=AsyncMock)
 @patch("prime_directive.bin.pd.get_session")
-def test_status_command(mock_dispose, mock_get_session, mock_init_db, mock_get_status, mock_load, mock_config):
+def test_status_command(mock_dispose, mock_get_session, mock_get_status, mock_load, mock_config):
```

</blockquote></details>
<details>
<summary>prime_directive/core/ai_providers.py (1)</summary><blockquote>

`28-68`: **Same inconsistency applies to `generate_openai_chat`.**

This function also mixes exception-based error handling (HTTP errors) with return-value error handling (missing/malformed response content). Consider unifying the approach for both functions.


Option 1 - Always raise:
```diff
     choices = data.get("choices")
     if not choices:
-        return "Error: No response from AI model."
+        raise ValueError("No choices in AI response")
```

Option 2 - Always return error strings (catch HTTP errors):
```diff
-    response.raise_for_status()
+    try:
+        response.raise_for_status()
+    except requests.HTTPError as e:
+        return f"Error: HTTP {e.response.status_code}"
```

</blockquote></details>
<details>
<summary>prime_directive/core/registry.py (4)</summary><blockquote>

`1-4`: **Unused import: `List`.**

The `List` type is imported but never used in this file.



```diff
-from typing import Dict, List, Optional
+from typing import Dict, Optional
```

---

`17-27`: **No-op validator adds complexity without value.**

The `validate_path` method returns the input unchanged. The extensive comments explain the rationale, but the validator itself does nothing. Either implement validation (even if just a warning) or remove the validator entirely to reduce confusion.



```diff
 class RepoConfig(BaseModel):
     id: str
     path: str
     priority: int
     active_branch: Optional[str] = None
-
-    @field_validator("path")
-    @classmethod
-    def validate_path(cls, v: str) -> str:
-        # Check if path exists - strictly we might want to allow non-existent paths if we are just configuring
-        # But the PRD says "Validate all repo paths exist"
-        # We'll make it a soft validation or just logged warning in a real app, 
-        # but for strict PRD adherence, let's keep it as is or check existence in the loader.
-        # Pydantic validation happens at instantiation.
-        # Let's assume for now we just validate it's a string. 
-        # Existence check is better done at runtime/loading to avoid crashing on config load if a drive is unmounted.
-        return v
+    # Note: Path existence validation is deferred to runtime/loading to avoid
+    # crashing on config load if a drive is unmounted or path is being configured.
```

---

`41-43`: **Fix inconsistent indentation.**

Line 42 has an extra leading space before the comment.



```diff
         else:
-             # Return default if no config found
+            # Return default if no config found
             return Registry()
```

---

`62-65`: **Fix inconsistent indentation.**

Lines 64-65 have extra leading spaces.



```diff
         for repo_id, repo_data in data["repos"].items():
             if isinstance(repo_data, dict):
-                 if "id" not in repo_data:
-                     repo_data["id"] = repo_id
+                if "id" not in repo_data:
+                    repo_data["id"] = repo_id
```

</blockquote></details>
<details>
<summary>prime_directive/bin/pd.py (3)</summary><blockquote>

`140-140`: **`datetime.utcnow()` is deprecated in Python 3.12+.**

Use `datetime.now(timezone.utc)` for timezone-aware datetimes. The `timezone` import is already available in `prime_directive/core/db.py`.



```diff
+from datetime import datetime, timezone
 ...
         snapshot = ContextSnapshot(
             repo_id=repo_id,
-            timestamp=datetime.utcnow(),
+            timestamp=datetime.now(timezone.utc),
```

---

`165-166`: **Chain the exception with `from` for better traceability.**

Per B904, re-raising within an `except` block should use `from` to preserve or explicitly suppress the exception chain.



```diff
         except ValueError:
-            raise typer.Exit(code=1)
+            raise typer.Exit(code=1) from None
```

---

`262-270`: **Fix inconsistent indentation in status icon logic.**

The `elif` blocks have extra leading spaces.



```diff
                     if git_st["is_dirty"]:
                         status_icon = "🔴"
                         status_text = f"Dirty ({len(git_st['uncommitted_files'])})"
                     elif git_st["branch"] == "unknown":
-                         status_icon = "⚪"
-                         status_text = "Not Git"
+                        status_icon = "⚪"
+                        status_text = "Not Git"
                     elif git_st["branch"] == "error":
-                         status_icon = "❌"
-                         status_text = "Error"
+                        status_icon = "❌"
+                        status_text = "Error"
                     elif git_st["branch"] == "timeout":
-                         status_icon = "⏱️"
-                         status_text = "Timeout"
+                        status_icon = "⏱️"
+                        status_text = "Timeout"
```

</blockquote></details>
<details>
<summary>prime_directive/core/db.py (2)</summary><blockquote>

`43-43`: **Move `os` import to top of file.**

Inline imports add overhead on each call and reduce code clarity.



```diff
+import os
 from datetime import datetime, timezone
 from typing import Optional, Dict
 ...
 def get_engine(db_path: str = "data/prime.db"):
     global _async_engines
     if db_path in _async_engines:
         return _async_engines[db_path]
     
     # Ensure directory exists
-    import os
     if db_path != ":memory:":
```

---

`71-77`: **Missing return type annotation on `get_session`.**

The function is an async generator but lacks the proper type hint.



```diff
+from typing import AsyncGenerator
+from sqlalchemy.ext.asyncio import AsyncSession
 ...
-async def get_session(db_path: str = "data/prime.db"):
+async def get_session(db_path: str = "data/prime.db") -> AsyncGenerator[AsyncSession, None]:
     engine = get_engine(db_path)
```

</blockquote></details>
<details>
<summary>prime_directive/core/scribe.py (3)</summary><blockquote>

`24-42`: **Clarify docstring to reflect OpenAI fallback behavior and accepted values.**

The docstring currently says this "Generates a SITREP summary using Ollama" but the function also supports an optional OpenAI fallback controlled by `fallback_provider`, `fallback_model`, and `require_confirmation`. It would be clearer to describe that primary vs fallback behavior and document what values `fallback_provider` is expected to take (e.g., `"none"` vs `"openai"`), plus how `require_confirmation` affects whether the fallback is actually attempted.



```diff
-    """
-    Generates a SITREP summary using Ollama.
+    """
+    Generates a SITREP summary using Ollama, with optional OpenAI fallback.
@@
-        fallback_provider (str): The fallback provider to use if Ollama fails.
-        fallback_model (str): The fallback model to use if Ollama fails.
-        require_confirmation (bool): Whether to require confirmation for OpenAI fallback.
+        fallback_provider (str): Fallback provider to use if Ollama fails (e.g., "none", "openai").
+        fallback_model (str): Model to use with the fallback provider.
+        require_confirmation (bool): If True, do not auto-call OpenAI; the caller must explicitly opt-in.
```

---

`48-63`: **Consider redacting sensitive data from git/terminal logs before sending to providers.**

`git_state`, `terminal_logs`, and `active_task` are injected verbatim into the prompt; depending on usage, these can contain secrets, tokens, or PII that will be forwarded to Ollama/OpenAI. If this might run against remote providers, consider adding a lightweight redaction/sanitization step or a config flag to strip or mask obviously sensitive patterns (tokens, emails, URLs with query params) before constructing the prompt.

---

`93-102`: **Make non-OpenAI error message resilient when `last_error` is unset.**

If `max_retries` were misconfigured to a negative value or a non-`RequestException` escaped the loop earlier, `last_error` could still be `None`, producing `"Error generating SITREP: None"`. It’s minor but easy to harden by falling back to a generic message when `last_error` is not set.



```diff
-    if fallback_provider != "openai":
-        return f"Error generating SITREP: {last_error!s}"
+    if fallback_provider != "openai":
+        message = str(last_error) if last_error is not None else "Unknown error contacting Ollama"
+        return f"Error generating SITREP: {message}"
```

</blockquote></details>

</blockquote></details>

<details>
<summary>📜 Review details</summary>

**Configuration used**: CodeRabbit UI

**Review profile**: CHILL

**Plan**: Pro

<details>
<summary>📥 Commits</summary>

Reviewing files that changed from the base of the PR and between 2791ce1c96d04aa191d5eb402666857a8a4beffd and 512bb8ef8776d9616fcf481f8e04f091c5cdc234.

</details>

<details>
<summary>📒 Files selected for processing (34)</summary>

* `.env.example` (1 hunks)
* `.github/ISSUE_TEMPLATE/bug_report.md` (1 hunks)
* `.github/ISSUE_TEMPLATE/feature_request.md` (1 hunks)
* `.github/PULL_REQUEST_TEMPLATE.md` (1 hunks)
* `.github/init.sh` (0 hunks)
* `.github/rename_project.sh` (0 hunks)
* `.github/workflows/main.yml` (4 hunks)
* `.github/workflows/rename_project.yml` (0 hunks)
* `.taskmaster/tasks/tasks.json` (1 hunks)
* `ABOUT_THIS_TEMPLATE.md` (0 hunks)
* `CONTRIBUTING.md` (1 hunks)
* `HISTORY.md` (1 hunks)
* `README.md` (1 hunks)
* `docs/PR_ISSUES_DEC14_2025.md` (1 hunks)
* `docs/index.md` (1 hunks)
* `mkdocs.yml` (1 hunks)
* `prime_directive/bin/pd.py` (1 hunks)
* `prime_directive/bin/pd_daemon.py` (1 hunks)
* `prime_directive/core/ai_providers.py` (1 hunks)
* `prime_directive/core/db.py` (1 hunks)
* `prime_directive/core/dependencies.py` (1 hunks)
* `prime_directive/core/logging_utils.py` (1 hunks)
* `prime_directive/core/registry.py` (1 hunks)
* `prime_directive/core/scribe.py` (1 hunks)
* `prime_directive/core/tasks.py` (1 hunks)
* `prime_directive/core/terminal.py` (1 hunks)
* `prime_directive/core/windsurf.py` (1 hunks)
* `pyproject.toml` (1 hunks)
* `tests/test_cli.py` (1 hunks)
* `tests/test_db.py` (1 hunks)
* `tests/test_freeze.py` (1 hunks)
* `tests/test_scribe.py` (1 hunks)
* `tests/test_terminal.py` (1 hunks)
* `tests/test_tmux.py` (1 hunks)

</details>

<details>
<summary>💤 Files with no reviewable changes (4)</summary>

* ABOUT_THIS_TEMPLATE.md
* .github/rename_project.sh
* .github/workflows/rename_project.yml
* .github/init.sh

</details>

<details>
<summary>✅ Files skipped from review due to trivial changes (2)</summary>

* docs/index.md
* HISTORY.md

</details>

<details>
<summary>🚧 Files skipped from review as they are similar to previous changes (3)</summary>

* tests/test_scribe.py
* .taskmaster/tasks/tasks.json
* prime_directive/bin/pd_daemon.py

</details>

<details>
<summary>🧰 Additional context used</summary>

<details>
<summary>🧠 Learnings (1)</summary>

<details>
<summary>📚 Learning: 2025-07-19T19:48:52.859Z</summary>

```
Learnt from: CR
Repo: ImmortalDemonGod/Holistic-Performance-Enhancement PR: 0
File: .windsurfrules:0-0
Timestamp: 2025-07-19T19:48:52.859Z
Learning: Environment variables required for the workflow (such as ANTHROPIC_API_KEY, MODEL, MAX_TOKENS, TEMPERATURE, DEBUG, TASKMASTER_LOG_LEVEL, DEFAULT_SUBTASKS, DEFAULT_PRIORITY, PROJECT_NAME, PROJECT_VERSION, PERPLEXITY_API_KEY, PERPLEXITY_MODEL) must be set in the environment or configuration files.
```

**Applied to files:**
- `.env.example`

</details>

</details><details>
<summary>🧬 Code graph analysis (3)</summary>

<details>
<summary>tests/test_tmux.py (1)</summary><blockquote>

<details>
<summary>prime_directive/core/tmux.py (2)</summary>

* `ensure_session` (5-81)
* `detach_current` (83-91)

</details>

</blockquote></details>
<details>
<summary>tests/test_terminal.py (1)</summary><blockquote>

<details>
<summary>prime_directive/core/terminal.py (1)</summary>

* `capture_terminal_state` (4-56)

</details>

</blockquote></details>
<details>
<summary>tests/test_cli.py (1)</summary><blockquote>

<details>
<summary>prime_directive/system/shell_integration.zsh (1)</summary>

* `pd` (7-9)

</details>

</blockquote></details>

</details><details>
<summary>🪛 dotenv-linter (4.0.0)</summary>

<details>
<summary>.env.example</summary>

[warning] 7-7: [QuoteCharacter] The value has quote characters (', ")

(QuoteCharacter)

---

[warning] 11-11: [QuoteCharacter] The value has quote characters (', ")

(QuoteCharacter)

---

[warning] 12-12: [EndingBlankLine] No blank line at the end of the file

(EndingBlankLine)

---

[warning] 12-12: [QuoteCharacter] The value has quote characters (', ")

(QuoteCharacter)

</details>

</details>
<details>
<summary>🪛 LanguageTool</summary>

<details>
<summary>docs/PR_ISSUES_DEC14_2025.md</summary>

[style] ~1569-~1569: You have already used this phrasing in nearby sentences. Consider replacing it to add variety to your writing.
Context: ...g] 6-6: [ValueWithoutQuotes] This value needs to be surrounded in quotes  (ValueWithoutQ...

(REP_NEED_TO_VB)

---

[style] ~1581-~1581: You have already used this phrasing in nearby sentences. Consider replacing it to add variety to your writing.
Context: ...g] 8-8: [ValueWithoutQuotes] This value needs to be surrounded in quotes  (ValueWithoutQ...

(REP_NEED_TO_VB)

---

[style] ~1599-~1599: You have already used this phrasing in nearby sentences. Consider replacing it to add variety to your writing.
Context: ... 10-10: [ValueWithoutQuotes] This value needs to be surrounded in quotes  (ValueWithoutQ...

(REP_NEED_TO_VB)

---

[style] ~1612-~1612: ‘new record’ might be wordy. Consider a shorter alternative.
Context: ...sk_024.txt</summary>  [style] ~24-~24: ‘new record’ might be wordy. Consider a shorter alt...

(EN_WORDINESS_PREMIUM_NEW_RECORD)

---

[style] ~1613-~1613: ‘new record’ might be wordy. Consider a shorter alternative.
Context: ...Modify the provider manager to insert a new record into the SQLite table each time an AI f...

(EN_WORDINESS_PREMIUM_NEW_RECORD)

---

[grammar] ~1622-~1622: Ensure spelling is correct
Context: ...ts 1.1-3.3. Amnesia Test: Work on repo1 30min, switch away 24h, pd switch repo1, comm...

(QB_NEW_EN_ORTHOGRAPHY_ERROR_IDS_1)

---

[style] ~1639-~1639: ‘Make a decision’ might be wordy. Consider a shorter alternative.
Context: ...sk_020.txt</summary>  [style] ~24-~24: ‘Make a decision’ might be wordy. Consider a shorter alt...

(EN_WORDINESS_PREMIUM_MAKE_A_DECISION)

---

[style] ~1640-~1640: ‘Make a decision’ might be wordy. Consider a shorter alternative.
Context: ... and integration with existing systems. Make a decision and document the rationale.  ## 3. Refa...

(EN_WORDINESS_PREMIUM_MAKE_A_DECISION)

---

[style] ~1649-~1649: Consider an alternative to strengthen your wording.
Context: ...s of focused integration work before it can be trusted for daily use.**  The architecture is s...

(CAN_BE_TRUSTED)

---

[style] ~1658-~1658: This phrase is redundant. Consider using “outside”.
Context: ... behavior of the workflow when executed outside of a tmux session using attach/exec. ### D...

(OUTSIDE_OF)

---

[style] ~1665-~1665: This phrase is redundant. Consider using “outside”.
Context: ...or executes a new tmux session when run outside of tmux, without blocking or security issu...

(OUTSIDE_OF)

</details>

</details>
<details>
<summary>🪛 markdownlint-cli2 (0.18.1)</summary>

<details>
<summary>CONTRIBUTING.md</summary>

107-107: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

</details>
<details>
<summary>.github/ISSUE_TEMPLATE/bug_report.md</summary>

16-16: Emphasis used instead of a heading

(MD036, no-emphasis-as-heading)

</details>
<details>
<summary>docs/PR_ISSUES_DEC14_2025.md</summary>

1-1: Emphasis used instead of a heading

(MD036, no-emphasis-as-heading)

---

112-112: Spaces inside code span elements

(MD038, no-space-in-code)

---

863-863: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

880-880: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

897-897: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

919-919: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

938-938: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

954-954: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

969-969: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

984-984: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

999-999: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1014-1014: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1029-1029: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1044-1044: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1059-1059: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1074-1074: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1089-1089: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1106-1106: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1121-1121: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1136-1136: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1151-1151: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1166-1166: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1181-1181: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1196-1196: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1211-1211: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1226-1226: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1241-1241: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1256-1256: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1271-1271: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1286-1286: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

---

1301-1301: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

</details>
<details>
<summary>README.md</summary>

101-101: Fenced code blocks should have a language specified

(MD040, fenced-code-language)

</details>

</details>
<details>
<summary>🪛 Ruff (0.14.8)</summary>

<details>
<summary>prime_directive/core/terminal.py</summary>

30-30: `subprocess` call: check for execution of untrusted input

(S603)

---

48-48: Consider moving this statement to an `else` block

(TRY300)

</details>
<details>
<summary>tests/test_db.py</summary>

23-23: Probable insecure usage of temporary file or directory: "/tmp/test"

(S108)

---

36-36: Probable insecure usage of temporary file or directory: "/tmp/test"

(S108)

---

43-43: Probable insecure usage of temporary file or directory: "/tmp/test"

(S108)

</details>
<details>
<summary>prime_directive/core/dependencies.py</summary>

37-37: Consider moving this statement to an `else` block

(TRY300)

</details>
<details>
<summary>tests/test_tmux.py</summary>

31-31: Probable insecure usage of temporary file or directory: "/tmp/tmux-1000/default,123,0"

(S108)

</details>
<details>
<summary>tests/test_freeze.py</summary>

31-31: Probable insecure usage of temporary file or directory: "/tmp/test-repo"

(S108)

---

42-42: Unused function argument: `mock_init_db`

(ARG001)

</details>
<details>
<summary>prime_directive/core/windsurf.py</summary>

22-22: `subprocess` call: check for execution of untrusted input

(S603)

</details>
<details>
<summary>tests/test_cli.py</summary>

32-32: Probable insecure usage of temporary file or directory: "/tmp/repo1"

(S108)

---

33-33: Probable insecure usage of temporary file or directory: "/tmp/repo2"

(S108)

---

52-52: Unused function argument: `mock_init_db`

(ARG001)

</details>

</details>

</details>

<details>
<summary>🔇 Additional comments (20)</summary><blockquote>

<details>
<summary>.github/ISSUE_TEMPLATE/feature_request.md (1)</summary><blockquote>

`1-6`: **Template metadata updated appropriately.**

The metadata header clearly identifies this as a feature request template with improved branding ("Prime Directive") and narrowed label scope (removed "question" label). Title default `[FEATURE]` provides good prefix for filtering and organization.

</blockquote></details>
<details>
<summary>mkdocs.yml (1)</summary><blockquote>

`1-4`: **Documentation site configuration looks good.**

The site metadata and theme configuration are properly structured. Using readthedocs as the theme is a solid choice for documentation projects.

</blockquote></details>
<details>
<summary>prime_directive/core/tasks.py (1)</summary><blockquote>

`15-24`: **LGTM: Robust file loading with proper error handling.**

The function correctly handles both missing files and invalid JSON, returning `None` in both cases. This defensive approach prevents crashes when the Task Master integration is not set up.

</blockquote></details>
<details>
<summary>prime_directive/core/windsurf.py (1)</summary><blockquote>

`19-26`: **Security consideration: subprocess call with configurable command is adequately mitigated.**

The `editor_cmd` from configuration is used safely in the subprocess call. While Ruff flags this as potentially untrusted input (S603), the implementation includes effective mitigations: (1) `shutil.which()` at line 14 validates the command exists in PATH before execution, restricting it to legitimate executables; (2) the list form prevents shell injection attacks; (3) the command originates from configuration, not runtime user input. No additional config-level validation is needed.

</blockquote></details>
<details>
<summary>.github/PULL_REQUEST_TEMPLATE.md (1)</summary><blockquote>

`1-18`: **LGTM! Template structure improved.**

The restructured PR template provides clearer section organization with standard Markdown headers and better guidance for contributors. The addition of explicit "Testing" and "Related Issues" sections encourages better documentation practices.

</blockquote></details>
<details>
<summary>tests/test_terminal.py (1)</summary><blockquote>

`1-61`: **LGTM! Comprehensive test coverage.**

The tests thoroughly validate `capture_terminal_state` behavior across multiple scenarios:
- Successful tmux capture with and without repo_id targeting
- Tmux failure handling  
- Missing tmux binary

The unused variable issues flagged in previous reviews have been addressed (lines 33, 60 use `_cmd` prefix).

</blockquote></details>
<details>
<summary>tests/test_db.py (1)</summary><blockquote>

`1-83`: **LGTM! Solid async ORM test coverage.**

The tests effectively validate:
- Repository CRUD operations
- ContextSnapshot creation with proper FK relationships
- FK constraint enforcement (IntegrityError on invalid repo_id)

The static analysis warnings (S108) about `/tmp/test` are false positives—these are literal string values assigned to the `path` field for test data, not actual file system operations. The fixture correctly uses `tmp_path` for the actual database file.

</blockquote></details>
<details>
<summary>tests/test_freeze.py (1)</summary><blockquote>

`87-92`: **LGTM! Clean negative test case.**

The invalid repository test properly validates error handling with appropriate exit code and error message.

</blockquote></details>
<details>
<summary>tests/test_tmux.py (1)</summary><blockquote>

`1-57`: **LGTM! Thorough tmux session management tests.**

The tests comprehensively cover:
- New session creation and attachment (outside tmux)
- Switching to existing session (inside tmux)
- Detach behavior with and without active tmux session

The static analysis warning (S108) at line 31 is a false positive—the `/tmp/tmux-1000/default,123,0` string is mock data for the `TMUX` environment variable, not a file system operation.

</blockquote></details>
<details>
<summary>tests/test_cli.py (2)</summary><blockquote>

`38-45`: **LGTM! Clean list command test.**

The test effectively validates repository listing output with priority values.

---

`97-126`: **LGTM! Comprehensive doctor command validation.**

The test effectively mocks multiple dependencies (tmux, code editor, Ollama API) and validates the diagnostic output. The `which_side_effect` pattern cleanly handles multiple command checks.

</blockquote></details>
<details>
<summary>prime_directive/core/dependencies.py (3)</summary><blockquote>

`10-31`: **LGTM! Clean dependency checking utilities.**

The `DependencyStatus` dataclass provides comprehensive state tracking, and the platform-specific installation commands handle macOS/Linux appropriately. The `is_ollama_installed` check is straightforward and correct.

---

`34-39`: **LGTM! Appropriate timeout and error handling.**

The Ollama running check properly handles request exceptions and uses a reasonable 2-second timeout.

---

`60-118`: **LGTM! Comprehensive status reporting with actionable guidance.**

The `get_ollama_status` function provides clear status messages and actionable commands (install, start, pull) for each failure mode. The `has_openai_api_key` check is straightforward. Note that the model matching issue flagged above affects line 94's call to `check_ollama_model_present`.

</blockquote></details>
<details>
<summary>prime_directive/core/ai_providers.py (1)</summary><blockquote>

`71-72`: **Clean implementation.**

The simplified `get_openai_api_key` is correct and follows the recommendation from the docs. The `or None` ensures empty strings are treated as absent.

</blockquote></details>
<details>
<summary>docs/PR_ISSUES_DEC14_2025.md (1)</summary><blockquote>

`1-2183`: **Documentation file - review notes archive.**

This file appears to be a record of prior AI-generated review comments and guidance. No functional code changes to review. Consider whether this file should be committed to the repository or maintained separately as review artifacts.

</blockquote></details>
<details>
<summary>prime_directive/core/registry.py (1)</summary><blockquote>

`33-67`: **`load_registry` handles format flexibility well.**

The function correctly handles both list and dict formats for repos, normalizes the structure, and provides sensible fallbacks. The logic is sound.

</blockquote></details>
<details>
<summary>prime_directive/bin/pd.py (1)</summary><blockquote>

`69-151`: **`freeze_logic` is well-structured with good mock mode support.**

The function cleanly separates concerns: Git capture, terminal capture, task retrieval, SITREP generation, and DB persistence. Mock mode support enables testing without external dependencies.

</blockquote></details>
<details>
<summary>prime_directive/core/db.py (2)</summary><blockquote>

`9-31`: **Well-designed ORM models with proper indexing.**

The models correctly define:
- Primary keys and foreign key relationships
- Composite index on `(repo_id, timestamp)` for efficient latest-snapshot queries
- Timezone-aware timestamp default using `datetime.now(timezone.utc)`
- Bidirectional relationships between Repository and ContextSnapshot

---

`79-91`: **`dispose_engine` handles cleanup correctly.**

The function properly handles both single-path disposal and disposing all cached engines. The pop-based approach prevents double-disposal.

</blockquote></details>

</blockquote></details>

</details>

<!-- This is an auto-generated comment by CodeRabbit for review status -->