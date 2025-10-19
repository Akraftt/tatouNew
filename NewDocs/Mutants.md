# Mutation Testing

## 1. Mutation-testing tool configuration

**Tool:** mutmut (3.3.1) with pytest runner

### Config: server/pyproject.toml

```ini
[tool.mutmut]
paths_to_mutate = ["src"]
tests_dir = ["test"]
runner = "python -m pytest -q"
backup = true
use_coverage = true
```

### Set up venv.

```ini
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m pip install mutmut pytest-cov
```

### Each iteration.

```ini
pytest -q
mutmut run
mutmut results | grep survived -n | sed -n '1,80p'
```

### Useful things/commands to know.

- `to exit .venv on VRA:`

```ini
deactivate 
```

- `To empty mutmuts cache:`

```ini
rm -rf ./mutants .mutmut-cache
find . -type d -name "__pycache__" -exec rm -rf {} +
```

## 2. Collection of interesting mutants identified
An unexpected issue was discovered where Mutmut itself, you could say, mutated the environment by caching a deleted test file, causing persistent failures. Personally, I found this quite interesting since it revealed that the testing tool itself can unintentionally affect or distort the test environment.

A large number of mutants survived in register_rmap_routes() primarily around handling and environment checks. What’s even more interesting is that when this was addressed, only the coverage increased, and the total amount of mutants stayed the same.

To start finding interesting mutants, I first navigated to the server directory (1), then activated the virtual environment (2) and ran Mutmut (3). After that, I began investigating by listing which mutants survived (4) and selecting one to inspect in detail (5). I repeated this process until I found an interesting mutant. I then created a test for it in VS Code and committed the change (6). Back on the VRA, I deactivated the virtual environment, pulled the new test, and ran it again. Steps 4–10 were repeated iteratively.

- `1. cd ~/tatouNew/server`
- `2. . .venv/bin/activate`
- `3. mutmut run`
- `4. mutmut results | nl | grep survived | sed -n '1,40p'`
- `5. mutmut show watermarking_cli.x__resolve_secret__mutmut_2`
- `6. Create a test in vscode & commit the test`
- `7. deactivate (on VRA)`
- `8. git pull`
- `9. . .venv/bin/activate`
- `10. mutmut run`

**Notable Mutants Identified:**

### Mutant #1: Key File Resolution Inverted

**File:** `watermarking_cli.py`  

**Severity:** Critical

This inversion changes the logic so that a key is only read from a file when no key was provided, this would break the watermarking (cli-based) entirely since key would always fail.

### Mutant #2: PDF Validation Exception Removed

**File:** `watermarking_method.py`  

**Severity:** High

by simply mutating the message to none the exception handling becomes ambiguous, this shows how eak assertions can be such as only cheaking exception type and missing data integrity.

### Mutant #3: Server Key Passphrase Removed

**File:** `rmap_service.py`  

**Severity:** Critical

This mutations removes the servers private key passphrase entirely, this would allow unencrypted key material to be loaded.

### Mutant #4: Secret File Resolution Inverted

**File:** `watermarking_cli.py`  

**Severity:** Critical

This inversion changed logic so that the secret is only read from a file when no file argument was provided, which in turn breaks the watermarking process.

## 3. Bugs discovered (tests & project)

The bug was discovered when trying to increase the number of mutants killed. However, the test file that was created started causing issues. After going back and forth trying to apply a fix, the decision was made to delete the new test file. The file was deleted in VS Code, and the change was pushed to GitHub. The VRA fetched the change, and the file was confirmed to be gone. However, when trying to execute Mutmut, the program still encountered the same error as before, despite the file not existing in GitHub, VS Code, or the VRA. As it turns out, Mutmut had a cached version of the file still residing inside the program that had to be removed manually. 

**Type of Bug:** Environment/test suite inconsistency
**Source:** Mutmut retained an obsolute test file inside its internal workspace.
**Symptom:** Mutmut runs failed with a reference to a non-existent functions.
**Impact** False negatives and it simply was not possible to run the program.
**Fix for the bug:** Remove ./mutants/ and .mutmut-cache such as:

```ini
rm -rf ./mutants .mutmut-cache
find . -type d -name "__pycache__" -exec rm -rf {} +
```

## 4. Collection of fixes

### Mutant #1: Key File Resolution Inverted

**Original Code:**
```python
if args.key_file is not None:
    return _read_text_from_file(args.key_file).strip("\n\r")
```

**Mutant:**
```python
if args.key_file is None:
    return _read_text_from_file(args.key_file).strip("\n\r")
```

**Test:**
```python
def test_resolve_key_from_file(tmp_path):
    f = tmp_path / "key.txt"
    f.write_text("abc123\n")
    args = types.SimpleNamespace(key=None, key_file=str(f), key_stdin=False)
    assert cli._resolve_key(args) == "abc123"
```
**Change:** Killed: 733 → 741

### Mutant #2: PDF Validation Exception Removed

**Original Code:**
```python
if not is_pdf_bytes(data):
    raise ValueError("Input does not look like a valid PDF (missing %PDF header)")
```

**Mutant:**
```python
if not is_pdf_bytes(data):
    raise ValueError(None)
```

**Test:**
```python
def test_invalid_pdf_error_message():
    with pytest.raises(ValueError, match="%PDF"):
        load_pdf_bytes(b"not a pdf")
```
**Change:** Killed: 741 → 743

### Mutant #3: Server Key Passphrase Removed

**Original Code:**
```python
server_private_key_passphrase = os.environ.get("RMAP_SERVER_PRIV_PASSPHRASE") or None,
```

**Mutant:**
```python
server_private_key_passphrase = None,
```

**Test:**
```python
def test_rmap_missing_payload_raises():
    from rmap_service import _read_payload_b64
    import flask
    with flask.Flask(__name__).test_request_context(data=""):
        with pytest.raises(Exception, match="payload"):
            _read_payload_b64()
```
**Change:** Killed: 743 → 746

### Mutant #4: Secret File Resolution Inverted

**Original Code:**
```python
if args.secret_file is not None:
    return _read_text_from_file(args.secret_file)
```

**Mutant:**
```python
if args.secret_file is None:
    return _read_text_from_file(args.secret_file)
```

**Test:**
```python
def test_resolve_secret_from_file(tmp_path):
    f = tmp_path / "secret.txt"
    f.write_text("hidden123\n")
    args = types.SimpleNamespace(secret=None, secret_file=str(f), secret_stdin=False)
    assert cli._resolve_secret(args) == "hidden123\n"
```

**Change:** Killed: 746 → 747

## 5. Concise findings

**Metrics progression (representative runs):** 
**Killed:** 671 → 746
**Survived:** 973 → 923
**Incompetent (incomplete):** 84 → 58
**Timeouts / not-sure: unchanged: 2** 0 → 2

An interesting observation is that there is not always a direct correlation between increased coverage and the number of killed mutations. Sometimes many new tests are added, but the number of killed mutations barely changes, while other times, just a few simple tests can lead to a large increase in killed mutations. For example, the following tests:

- `test_initiate_no_payload()`
- `test_get_link_misconfig()`
- `test_get_link_bad_method()`

raised the coverage of src\rmap_service.py from 33% to 45%, even though the total number of killed mutants remained the same at 746.