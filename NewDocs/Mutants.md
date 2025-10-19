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