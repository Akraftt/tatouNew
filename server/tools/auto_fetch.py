#!/usr/bin/env python3
# batch_rmap_fetch_custom.py
# Lightweight RMAP batch fetcher (custom version for Group_26)
# Minimal dependencies: requests, pgpy

from pathlib import Path
import json, base64, secrets, time
import requests
from pgpy import PGPKey, PGPMessage

# ======= configuration (edit for your group) =======
MY_ID = "Group_26"                       # your identity
CLIENT_PRIV = Path("/home/lab/Desktop/g26_private.asc")
CLIENT_PASSPHRASE = "123"                # your private key passphrase (or None)

PEER_PUB_DIR = Path("/home/lab/tatou_peer_pubs")  # where to cache fetched server_pub files
PEER_PUB_DIR.mkdir(parents=True, exist_ok=True)

# candidate locations to try fetching server_pub.asc from the target
PUB_PATHS = [
    "/server_pub.asc",
    "/keys/server_pub.asc",
    "/static/server_pub.asc",
    "/tatou_keys/server_pub.asc",
]

PORT = 5000
TIMEOUT = 6
RETRIES = 2
SLEEP = 0.3

DOWNLOAD_DIR = Path("./downloads_custom")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# target list found from rmap
TARGETS = [
    ("Group_08", "10.11.12.7"),
    ("Group_20", "10.11.12.9"),
    ("Group_11", "10.11.12.11"),
    ("Group_14", "10.11.12.14"),
    ("Group_19", "10.11.12.17"),
    ("Group_18", "10.11.12.18"),
    ("Group_20_alt", "10.11.12.20"),
]


def is_pubkey_blob(s: str) -> bool:
    return "BEGIN PGP PUBLIC KEY BLOCK" in s

def local_pub_path(name: str) -> Path:
    return PEER_PUB_DIR / f"{name}.asc"

def try_fetch_peer_pub(ip: str, name: str) -> Path | None:
    base = f"http://{ip}:{PORT}"
    for p in PUB_PATHS:
        url = base + p
        try:
            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code == 200 and is_pubkey_blob(r.text):
                dst = local_pub_path(name)
                dst.write_text(r.text)
                print(f"[INFO] saved {name} server_pub from {url} -> {dst}")
                return dst
        except Exception:
            pass
    return None

def find_or_download_pub(name: str, ip: str) -> Path | None:
    p = local_pub_path(name)
    if p.exists():
        return p
    print(f"[INFO] no cached server_pub for {name}, attempting fetch from {ip}")
    return try_fetch_peer_pub(ip, name)

def encrypt_for_peer(plain: dict, server_pub_path: Path) -> str:
    pub, _ = PGPKey.from_file(str(server_pub_path))
    msg = PGPMessage.new(json.dumps(plain))
    enc = pub.encrypt(msg)
    return base64.b64encode(str(enc).encode()).decode()

def decrypt_from_peer(payload_any, priv_path: Path, passphrase: str | None):
    priv, _ = PGPKey.from_file(str(priv_path))
    if passphrase:
        priv.unlock(passphrase)

    if not isinstance(payload_any, (str, bytes)):
        raise ValueError("unexpected payload type")

    payload = payload_any if isinstance(payload_any, str) else payload_any.decode("latin1", errors="ignore")
    try:
        raw = base64.b64decode(payload, validate=False)
        try:
            armored = raw.decode("utf-8")
            pgp = PGPMessage.from_blob(armored)
        except UnicodeDecodeError:
            pgp = PGPMessage.from_blob(raw)
    except Exception:
        pgp = PGPMessage.from_blob(payload)

    decrypted = priv.decrypt(pgp).message
    return json.loads(decrypted)

def post_with_retry(url, body):
    for attempt in range(RETRIES):
        try:
            r = requests.post(url, json=body, timeout=TIMEOUT)
            if r.status_code == 405:
                r = requests.get(url, timeout=TIMEOUT)
            return r
        except Exception as e:
            if attempt + 1 < RETRIES:
                time.sleep(SLEEP)
            else:
                raise

def run_target(name: str, ip: str):
    print(f"\n=== {name} @ {ip} ===")
    server_pub = find_or_download_pub(name, ip)
    if server_pub is None:
        print(f"[SKIP] no server_pub for {name}")
        return {"group": name, "ip": ip, "ok": False, "reason": "no_server_pub"}

    base = f"http://{ip}:{PORT}"
    init_routes = [f"{base}/api/rmap-initiate", f"{base}/rmap-initiate", f"{base}/initiate", f"{base}/api/rmap-initiate/"]
    getlink_routes = [f"{base}/api/rmap-get-link", f"{base}/rmap-get-link", f"{base}/get-link"]

    nc = secrets.randbits(48)
    m1 = {"nonceClient": nc, "identity": MY_ID}
    payload1 = encrypt_for_peer(m1, server_pub)

    r1 = None
    for u in init_routes:
        try:
            r1 = post_with_retry(u, {"payload": payload1})
            print(f"[<-] {u} -> {r1.status_code} {str(r1.text)[:120]}")
            if r1.status_code == 200:
                break
        except Exception as e:
            print(f"[ERR] init {u}  {e}")
            continue
    if r1 is None or r1.status_code != 200:
        return {"group": name, "ip": ip, "ok": False, "reason": f"init_fail({r1.status_code if r1 else 'no_resp'})"}

    # parse r1 payload
    try:
        d1 = r1.json()
    except Exception:
        return {"group": name, "ip": ip, "ok": False, "reason": "bad_json_init"}
    if "payload" not in d1:
        return {"group": name, "ip": ip, "ok": False, "reason": d1}

    try:
        resp1 = decrypt_from_peer(d1["payload"], CLIENT_PRIV, CLIENT_PASSPHRASE)
    except Exception as e:
        return {"group": name, "ip": ip, "ok": False, "reason": f"decrypt_err:{e}"}

    ns = resp1.get("nonceServer")
    if ns is None:
        return {"group": name, "ip": ip, "ok": False, "reason": "no_nonceServer"}

    m2 = {"nonceServer": int(ns)}
    payload2 = encrypt_for_peer(m2, server_pub)

    r2 = None
    for u in getlink_routes:
        try:
            r2 = post_with_retry(u, {"payload": payload2})
            print(f"[->] {u} -> {r2.status_code}")
            if r2.status_code == 200:
                break
        except Exception as e:
            print(f"[ERR] getlink {u} {e}")
            continue

    if r2 is None or r2.status_code != 200:
        return {"group": name, "ip": ip, "ok": False, "reason": f"getlink_fail({r2.status_code if r2 else 'no_resp'})"}

    try:
        d2 = r2.json()
    except Exception:
        return {"group": name, "ip": ip, "ok": False, "reason": "bad_json_getlink"}

    candidates = []
    if "url" in d2:
        candidates = [d2["url"]]
    elif "result" in d2:
        sid = d2["result"]
        candidates = [f"{base}/dl/{sid}.pdf", f"{base}/api/get-version/{sid}", f"{base}/api/get-version/{sid}.pdf"]
    else:
        return {"group": name, "ip": ip, "ok": False, "reason": d2}

    for du in candidates:
        try:
            rr = requests.get(du, timeout=TIMEOUT)
            print(f"[DEBUG] {du} -> {rr.status_code} {rr.headers.get('Content-Type','')}")
            if rr.status_code == 200 and rr.headers.get("Content-Type","").startswith("application/pdf"):
                out = DOWNLOAD_DIR / f"{name}_{ip}.pdf"
                out.write_bytes(rr.content)
                print(f"[OK] downloaded -> {out}")
                return {"group": name, "ip": ip, "ok": True, "file": str(out)}
        except Exception as e:
            print(f"[DEBUG] download err {e}")

    return {"group": name, "ip": ip, "ok": False, "reason": "download_failed"}

def main():
    print("custom batch fetch start")
    results = []
    for nm, ip in TARGETS:
        res = run_target(nm, ip)
        results.append(res)
        time.sleep(0.2)
    import csv
    with open("batch_custom_results.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["group","ip","ok","file","reason"])
        writer.writeheader()
        for r in results:
            writer.writerow({"group": r.get("group"), "ip": r.get("ip"), "ok": r.get("ok"), "file": r.get("file",""), "reason": r.get("reason","")})
    print("done. results -> batch_custom_results.csv")

if __name__ == "__main__":
    main()
