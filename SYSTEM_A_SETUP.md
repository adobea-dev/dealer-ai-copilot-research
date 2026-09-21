# System A — Setup and Run

System A is the conventional single-shot Text-to-SQL baseline.

Architecture:

User question -> one Gemini call -> one SQL query -> PostgreSQL -> raw result

It deliberately has:
- no retry;
- no SQL self-repair;
- no planning loop;
- no tools beyond database execution;
- no explanation;
- no visualization.

## 1. Install the Google Gen AI SDK

From the active `dealerai-env` environment:

```powershell
pip install -U google-genai
```

Then add this package to your existing `requirements.txt` rather than
replacing that file.

## 2. Set the API key

For the current PowerShell session:

```powershell
$env:GEMINI_API_KEY="YOUR_KEY_HERE"
```

Do not commit the key to Git.

## 3. Freeze the model configuration

Recommended current configuration:

```powershell
$env:GEMINI_MODEL="gemini-3.8-flash"
$env:GEMINI_THINKING_LEVEL="medium"
```

Use the same base model and thinking level later for Systems B and C unless
the experimental protocol explicitly changes.

## 4. Ensure PostgreSQL environment variables are set

Example:

```powershell
$env:PGHOST="localhost"
$env:PGPORT="5432"
$env:PGDATABASE="dealer_ai_copilot"
$env:PGUSER="postgres"
```

If your existing connection helper requests the password interactively, that
can remain unchanged.

## 5. Test ONE development task first

```powershell
python -m scripts.run_system_a --task-id C1_DEV_01
```

## 6. Then run all 12 development tasks

```powershell
python -m scripts.run_system_a
```

Results are saved under:

```text
results/system_a/
```

## Important research rule

Do NOT run:

```powershell
python -m scripts.run_system_a --split test --allow-test
```

during development.

The 36 held-out tasks remain locked until Systems A, B, and C are frozen.

## Interpretation

`execution_success = true` means only that PostgreSQL executed the model's
query successfully.

It does not mean the analytical result is correct.

Correctness is determined later by comparing the returned result against the
frozen benchmark gold result using the common evaluator.
