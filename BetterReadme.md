This file will give step for step instructions

------------------------------------------------------------------------------------------------------------------------

Basic Docker Stuff:

1. See whats running:
docker compose ps

2. Start:
docker compose start

3. Stop:
docker compose stop

4. Restart:
docker compose restart

5. Apply config:
docker compose up -d

6. Rebuild:
docker compose up -d --build

7. Open phpmyadmin from terminal
start http://127.0.0.1:8081/

------------------------------------------------------------------------------------------------------------------------

RMAP POST Inside container

1. See what method is being used:
docker compose exec server sh -lc 'printenv RMAP_METHOD'

2. Check health (vscode):
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5000/healthz

3. RMAP Handshake:
docker compose exec -T server sh -lc "cd /app/src && python - <<'PY'
import os, json, base64, urllib.request, secrets
from rmap.identity_manager import IdentityManager
from pgpy import PGPKey, PGPMessage
base='http://127.0.0.1:5000'
im=IdentityManager(client_keys_dir=os.environ['RMAP_CLIENT_KEYS_DIR'],server_public_key_path=os.environ['RMAP_SERVER_PUB'],server_private_key_path=os.environ['RMAP_SERVER_PRIV'],server_private_key_passphrase=os.environ.get('RMAP_SERVER_PRIV_PASSPHRASE'))
jean_priv,_=PGPKey.from_file('/app/secrets/clients/Jean_private.asc')
def post(p,o): r=urllib.request.Request(base+p,data=json.dumps(o).encode(),headers={'Content-Type':'application/json'}); return json.loads(urllib.request.urlopen(r).read().decode())
nc=secrets.randbits(64)
r1=post('/api/rmap-initiate',{'payload':im.encrypt_for_server({'nonceClient':int(nc),'identity':'Jean'})})
arm=base64.b64decode(r1['payload'])
ns=int(json.loads(jean_priv.decrypt(PGPMessage.from_blob(arm)).message)['nonceServer'])
r2=post('/api/rmap-get-link',{'payload':im.encrypt_for_server({'nonceServer':ns})})
print('TOKEN='+r2['result'])
print('URL=http://127.0.0.1:5000/api/get-version/'+r2['result'])
PY"

4. Download the PDF:
$token = "a93e69539d20a1821cc2555877cccbdc"
Invoke-WebRequest -Uri "http://127.0.0.1:5000/api/get-version/$token" -OutFile .\wm.pdf
Get-Item .\wm.pdf

5. Verify the watermark
docker compose exec server sh -lc "cd /app/src && python - <<'PY'
from pathlib import Path
import os, watermarking_utils as WM
p = max(Path('/app/storage/uploads/watermarks').glob('*.pdf'), key=lambda x: x.stat().st_mtime)
print('Method in env:', os.environ.get('RMAP_METHOD'))
print('Checking:', p.name)
print('Recovered:', WM.read_watermark('anton-eof', p, 'course-demo-key'))
PY"

6. Confirm database entry
docker compose exec -T db `
  mariadb -uroot -prootpassword -D tatou `
  -e "SELECT id, name, path, ownerid, size, HEX(sha256) AS sha FROM Documents"

------------------------------------------------------------------------------------------------------------------------