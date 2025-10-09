# client_rmap.py - run from your Windows host, not inside Docker

# Python 3.13 shim (PGPy imports imghdr)
try:
    import imghdr  # noqa
except Exception:
    import types
    imghdr = types.SimpleNamespace(what=lambda *a, **k: None)  # noqa

import argparse, os, json, base64, urllib.request, secrets, getpass
from pgpy import PGPKey, PGPMessage

def load_key(path):
    key, _ = PGPKey.from_file(path)
    return key

def post(base, path, obj):
    data = json.dumps(obj).encode()
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read().decode())

def encrypt_for_server(server_pub, obj):
    msg = PGPMessage.new(json.dumps(obj))
    enc = server_pub.encrypt(msg)
    return base64.b64encode(str(enc).encode()).decode()

def decrypt_from_server(client_priv, b64payload):
    arm = base64.b64decode(b64payload)
    dec = client_priv.decrypt(PGPMessage.from_blob(arm))
    return json.loads(dec.message)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-u", "--base", default="http://127.0.0.1:5000")
    ap.add_argument("-i", "--identity", required=True)
    ap.add_argument("-s", "--server-pub", required=True)
    ap.add_argument("-k", "--client-priv", required=True)
    ap.add_argument("-p", "--passphrase", help="passphrase for the client private key (omit to be prompted)")
    ap.add_argument("-o", "--out")
    args = ap.parse_args()

    server_pub  = load_key(args.server_pub)
    client_priv = load_key(args.client_priv)

    # Unlock private key if protected
    if getattr(client_priv, "is_protected", False):
        pw = args.passphrase or getpass.getpass("Key passphrase: ")
        client_priv.unlock(pw)

    nc = secrets.randbits(64)
    r1 = post(args.base, "/api/rmap-initiate", {
        "payload": encrypt_for_server(server_pub, {"nonceClient": int(nc), "identity": args.identity})
    })
    ns = int(decrypt_from_server(client_priv, r1["payload"])["nonceServer"])

    r2 = post(args.base, "/api/rmap-get-link", {
        "payload": encrypt_for_server(server_pub, {"nonceServer": ns})
    })
    token = r2["result"]
    url = f"{args.base}/api/get-version/{token}"
    print("TOKEN=" + token)
    print("URL=" + url)

    if args.out:
        with urllib.request.urlopen(url) as resp:
            open(args.out, "wb").write(resp.read())
        print("Saved:", os.path.abspath(args.out))

if __name__ == "__main__":
    main()
