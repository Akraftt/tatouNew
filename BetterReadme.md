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

1. Verify the existance of pub keys:
docker compose exec server sh -lc 'echo RMAP_METHOD=$RMAP_METHOD; echo RMAP_CLIENT_KEYS_DIR=$RMAP_CLIENT_KEYS_DIR; ls -1 /app/secrets/clients | sed -n "1,20p"'

2. confirm path
cd C:\Users\Anton\sec\tatou

3. 
$py = @'
import json, base64, secrets, urllib.request
from pathlib import Path
from pgpy import PGPKey, PGPMessage

BASE = "http://127.0.0.1:5000"

SERVER_PUB = r"C:\Users\Anton\sec\tatou\secrets\server_pub.asc"
CLIENT_PRIV = r"C:\Users\Anton\Desktop\Group_50_private.asc"

server_pub, _ = PGPKey.from_file(SERVER_PUB)
client_priv, _ = PGPKey.from_file(CLIENT_PRIV)

def post(path, obj):
    data = json.dumps(obj).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())

def encrypt_for_server(obj):
    msg = PGPMessage.new(json.dumps(obj))
    enc = server_pub.encrypt(msg)
    return base64.b64encode(str(enc).encode()).decode()

def decrypt_from_server(b64payload):
    arm = base64.b64decode(b64payload)
    dec = client_priv.decrypt(PGPMessage.from_blob(arm))
    return json.loads(dec.message)

identity = "Group_50"
nc = secrets.randbits(64)

r1 = post("/api/rmap-initiate", {"payload": encrypt_for_server({"nonceClient": int(nc), "identity": identity})})
ns = int(decrypt_from_server(r1["payload"])["nonceServer"])

r2 = post("/api/rmap-get-link", {"payload": encrypt_for_server({"nonceServer": ns})})
token = r2["result"]

print("TOKEN=" + token)
print("URL=" + f"{BASE}/api/get-version/{token}")

out = Path("g50_wm.pdf")
with urllib.request.urlopen(f"{BASE}/api/get-version/{token}") as resp:
    out.write_bytes(resp.read())
print("Saved:", out.resolve())
'@

Set-Content -Path .\client_group50.py -Value $py -Encoding UTF8

py -3 .\client_group50.py

------------------------------------------------------------------------------------------------------------------------


PS C:\Users\Anton\sec\tatou> py -3 .\client_rmap.py `
>>   -u http://127.0.0.1:5000 `
>>   -i Group_50 `
>>   -s "C:\Users\Anton\sec\tatou\secrets\server_pub.asc" `
>>   -k "C:\Users\Anton\Desktop\Group_50_private.asc" `
>>   -u http://127.0.0.1:5000 `



------------------------------------------------------------------------------------------------------------------------
------------------------------------------------------------------------------------------------------------------------
------------------------------------------------------------------------------------------------------------------------
------------------------------------------------------------------------------------------------------------------------

SECURITY FIXES

1. Issue: 
Missing ownership enforcement in read-watermark allowed authenticated users to read secrets from documents they do not own.
2. Where: 
server/src/server.py
SELECT id, name, path FROM Documents WHERE id = :id
3. Severity: 
High. Any logged in user on VLAN could enumrate document ids and rcover watermarks or error messages.
4. Fix:
SELECT id, name, path FROM Documents
WHERE id = :id AND ownerid = :uid
5. Test:

1. Step: Create two users and a token such as:
$u1 = @{ email="alice@example.com"; login="alice"; password="alicepw" } | ConvertTo-Json
$null = Invoke-RestMethod -Uri http://127.0.0.1:5000/api/create-user -Method POST -Body $u1 -ContentType "application/json"
$u1login = @{ email="alice@example.com"; password="alicepw" } | ConvertTo-Json
$u1tok = (Invoke-RestMethod -Uri http://127.0.0.1:5000/api/login -Method POST -Body $u1login -ContentType "application/json").token

$u2 = @{ email="bob@example.com"; login="bob"; password="bobpw" } | ConvertTo-Json
$null = Invoke-RestMethod -Uri http://127.0.0.1:5000/api/create-user -Method POST -Body $u2 -ContentType "application/json"
$u2login = @{ email="bob@example.com"; password="bobpw" } | ConvertTo-Json
$u2tok = (Invoke-RestMethod -Uri http://127.0.0.1:5000/api/login -Method POST -Body $u2login -ContentType "application/json").token

2. Step: Create a PDF.
[IO.File]::WriteAllBytes("$PWD\alice.pdf",[Convert]::FromBase64String("JVBERi0xLjQKMSAwIG9iago8PCAvVHlwZSAvQ2F0YWxvZyA+PgplbmRvYmoKJSVFT0YK"))

3. Step: Upload the PDF as Alice.
$uri = "http://127.0.0.1:5000/api/upload-document"
$hdr = "Authorization: Bearer $u1tok"
$json = & curl.exe -s -H "$hdr" -F "file=@`"$PWD\alice.pdf`";type=application/pdf" -F "name=alice.pdf" $uri
$json
$docA = $json | ConvertFrom-Json
$docId = [int]$docA.id
$docId

4. Step: Try to access the PDF as Bob, Expected outcome: 404 {"error":"document not found"}
$rwBody = @{ method="anton-eof"; key="course-demo-key"; position="" } | ConvertTo-Json
try {
  Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/read-watermark/$docId" -Method POST -Headers @{ Authorization = "Bearer $u2tok" } -Body $rwBody -ContentType "application/json"
} catch {
  $_.Exception.Response.StatusCode.value__       # expect 404
  $_.ErrorDetails.Message                        # should contain "document not found"
}

5. Try to access it as Alice, Expected outcome: 400
try {
  Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/read-watermark/$docId" -Method POST -Headers @{ Authorization = "Bearer $u1tok" } -Body $rwBody -ContentType "application/json"
} catch {
  $_.Exception.Response.StatusCode.value__       # expect 400
}