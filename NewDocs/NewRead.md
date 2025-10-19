# Tatou (Group 26)

## 1. Prerequisites

- **Docker** and **Docker Compose**
- **Python 3.12+** (for local dev without containers)
- **Git**

## 2. Quick Start (Docker)

```ini
docker compose down
docker compose build server
docker compose up -d
```

**health-check**

```ini
curl -s http://127.0.0.1:5000/healthz
```

**Database sanity check (optional)**

```ini
docker compose exec db mariadb -u root -p tatou \
  -e "SELECT id,name FROM Documents ORDER BY id;"
```

## 3. Configuration

/app
  ├─ src/
  ├─ secrets/
  │   ├─ server_pub.asc
  │   ├─ server_priv.asc
  │   └─ clients/              # peer public keys (Group_XX.asc)
  └─ watermarks/               # generated PDFs

  Most configuration is provided through environment variables such as in docker-compose.yml or .env

- `RMAP_CLIENT_KEYS_DIR` – directory containing client public keys
- `RMAP_SERVER_PUB` – server public key path
- `RMAP_SERVER_PRIV` – server private key path
- `RMAP_SERVER_PRIV_PASSPHRASE` – passphrase for the private key
- `RMAP_SOURCE_DOC_ID` – numeric ID of the PDF document to watermark
- `RMAP_METHOD` – watermark method, such as BetterEOF
- `RMAP_WM_KEY` – server-side watermarking key/secret

## 4. Running Locally

```ini
cd server
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

## 5. Unit Tests & Coverage

**Test Environment Setup**

```ini
python -m venv .venv
& .venv\Scripts\python.exe -m pip install -U pip
& .venv\Scripts\python.exe -m pip install -e ".[dev]"
& .venv\Scripts\python.exe -m pip install pytest-cov
```

**Test Execution and Coverage Results**

```ini
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
. .\.venv\Scripts\Activate.ps1
cd server
& .venv\Scripts\python.exe -m pytest -q
& .venv\Scripts\python.exe -m pytest --cov=src --cov-report=term-missing
```

## 6. Mutation Testing (mutmut)

**pull new tests and activate virtual enviroment**

```ini
deactivate
cd ~/tatouNew/server
gitpull
python3 -m venv .venv
. .venv/bin/activate

```

**Fix cache issue - gets tale**

```ini
rm -rf ./mutants .mutmut-cache
find . -type d -name "__pycache__" -exec rm -rf {} +
```

**Typical iteration**

```ini
pytest -q
mutmut run
mutmut results | grep survived -n | sed -n '1,80p'
# inspect a specific mutant by name printed above:
mutmut show watermarking_cli.x__resolve_secret__mutmut_2
```

## 7. API Tests (manual examples)

**Healthz**

```ini
curl -s http://127.0.0.1:5000/healthz
```

**RMAP client flow (example):**

```ini
# Adjust IPs and paths for your environment
python3 client_rmap.py \
  -u http://10.11.12.12:5000 \
  -i Group_26 \
  -s ./secrets/server_pub.asc \
  -k ~/Desktop/g26_private.asc \
  -p 123 \
  -o ~/Desktop/g26_self_wm.pdf

# Verify watermark can be extracted with BetterEOF
python3 server/src/watermarking_cli.py extract ~/Desktop/g26_self_wm.pdf \
  --method BetterEOF --key "course-demo-key"
```

- `-u` – server base URL
- `-i` – identity of the requesting group (must exist in /app/secrets/clients)
- `-s` – server public key path
- `-k` – client private key path
- `-p` – passphrase for client key
- `-o` – output path for resulting PDF

## 8. Deployment

**Build images and run with**

- `docker compose up -d`

**Ensure secrets are mounted read-only with correct permissions:**

- `server_priv.asc` → 600, owned by root
- `server_pub.asc` → 644, owned by root
- `secrets/clients` → public keys for peers