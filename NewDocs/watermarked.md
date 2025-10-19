unfortunately i cannot get 10 watermarked pdf files. I tried doing all of this roughly 36 hours before the deadline, this is the steps ive took:


**Host discovery**

```ini
nmap -sn -oN /tmp/nmap_hosts.txt 10.11.12.0/24
```

Found 9: 10.11.12.{7,9,11,12,14,17,18,19,20}

**Service scan (expected ports)**

```ini
nmap -sV -p 22,80,443,5000,8000,8080,8443 \
  -oA /tmp/nmap_services \
  10.11.12.7 10.11.12.9 10.11.12.11 10.11.12.12 10.11.12.14 10.11.12.17 10.11.12.18 10.11.12.19 10.11.12.20
```

- `5000/tcp open` – 10.11.12.{7,9,11,12,14,17,18}
- `8080/tcp http:` – 10.11.12.{7,9,11,14,17,20}
- `80/tcp http:` – 10.11.12.14 (nginx)

**Check HTTP roots on port 5000**

```ini
for ip in 10.11.12.7 10.11.12.9 10.11.12.11 10.11.12.12 10.11.12.14 10.11.12.17 10.11.12.18; do
  curl -s -D - http://$ip:5000/ -o /dev/null | sed -n '1,12p'
done
```

 `All respond 200 OK with Gunicorn/Werkzeug index.`

 **Probe RMAP endpoints existence (10.11.12.14)**

 ```ini
curl -s -D - http://10.11.12.14:5000/api/rmap-initiate \
  -H 'Content-Type: application/json' \
  -d '{"payload":"invalid"}' | sed -n '1,60p'
```

 `HTTP/1.1 400 BAD REQUEST body: {"error":"handle_message1 failed: Incorrect padding"}`

  **Attempt to auto-discover peers’ server public key files**

Paths tried (both server_public.asc and server_pub.asc) on ports 5000 and 8080:

```ini
/server_public.asc
/rmap/server_public.asc
/tatou_keys/server_public.asc
/keys/server_public.asc
/static/server_public.asc
/public/server_public.asc
/pgp/server_public.asc
/api/server-public
/rmap/server-public
/server-pub.asc
/server_pub.asc
/keys/server_pub.asc
/static/server_pub.asc
```

```ini
for ip in ...; for port in 5000 8080; do
  for path in /server_public.asc /rmap/server_public.asc /keys/server_public.asc /static/server_public.asc /public/server_public.asc /pgp/server_public.asc /api/server-public /rmap/server-public /server-pub.asc /server_pub.asc /keys/server_pub.asc /static/server_pub.asc; do
    curl -fsS "http://$ip:$port$path"
  done
done
```

 `Result: no key found on any host`

   **Try helper script (tools/auto_fetch.py)**

```ini
cd ~/tatouNew/server/tools
python3 auto_fetch.py
```

 `[SKIP] no server_pub for Group_*`

   **Confirm our local end-to-end works (proof)**

 ```ini
cd ~/tatouNew/server
python3 ../client_rmap.py \
  -u http://127.0.0.1:5000 \
  -i Group_26 \
  -s ~/tatouNew/secrets/server_pub.asc \
  -k /home/lab/Desktop/g26_private.asc \
  -p 123 \
  -o /tmp/self_wm.pdf \
  --debug
```

Output:

 ```ini
TOKEN=<32-hex>
URL=http://127.0.0.1:5000/api/get-version/<32-hex>
Saved: /tmp/self_wm.pdf
```

 **Manual attempt against 10.11.12.14 using discovered paths**

`Key fetch: none (404/403 on all tested paths)*`

`Endpoint POST with bogus payload: 400 Incorrect padding (expected without their public key)`

 **Why i think it failed**

 As we know the RMAP requires encrypting to the peer’s server public key and typically the peer must have our client public key installed under their client, like i do.

 None of the peers publish a server public key at common URLs; auto_fetch.py also found nothing.

 Also when 123 was removed from -p 123 the program prompted for a passphrase, but inputting 123 (known correct passphrase) produced “incorrect passphrase”, even though verification via gpg --pinentry-mode loopback --import proves that 123 is the correct key password.

