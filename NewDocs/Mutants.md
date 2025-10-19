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


