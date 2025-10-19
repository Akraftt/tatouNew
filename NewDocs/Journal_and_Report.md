# Tatou – Phase I–III Report & Journal (Group 26)

**Member:** Solo contributor (Group 26)  
**Repository & Environment:** Ubuntu VRA, Python 3.12, Docker + Compose

# Reflection of the project as a whole.

Overall, I feel proud of what I’ve accomplished as a sole member of my group. The work has been a bit erratic, to say the very least, but I think things turned out somewhat fine in the end. It’s easy to look back and see all the mistakes you’ve made throughout the project, but in a way, that’s what we learn the most from. For example, for the longest time, I thought that RMAP_SOURCE_DOC_ID was supposed to be dynamic as opposed to the current static RMAP_SOURCE_DOC_ID = 2. I imagined that other groups were supposed to upload their own personal PDF to my database and get a watermarked copy in return. This issue kept me up for a few nights, embarrassingly enough. And this issue was the main reason my RMAP implementation was behind the phase 2 deadline, and due to this, I imagined not many groups were able to watermark against my VRA because of this. However, funnily enough, in a way, it was the reason I struggled so much to watermark against theirs, because now that the time limit for the hand-in is running short, many have probably started to turn their VRA off to hand in the project.

--- 

## 1. PHASE I – Warming Up.

For phase one, my primary goal was to become familiar with the codebase, environment, and workflow using Git and Docker. It had been a while since I used those two, so I took things rather slowly at first. I began by forking the repository, which was a mistake in hindsight, and then set up my Virtual Research Appliance (VRA) environment with Ubuntu, Python 3.12, and Docker Compose. After cloning, I verified that the core functionality worked as intended. This included confirming that the database was accessible and that the API endpoints functioned correctly. In hindsight, I should have verified these functionalities by writing tests instead of doing it manually. And, of course, the flags were inserted in their proper locations.

--- 

## 2. PHASE II – RMAP Endpoints and Watermarking.

For phase two there were a couple of main things we were supposed to do. One of which was to create our own watermarking system and sequentially implement two RMAP endpoints which other groups on the same VLAN could access.

### Phase two primarily focused on two main things:
**1. Implementing a custom watermarking technique.**

**2. Implementing two RMAP endpoints.**

### RMAP Endpoints Implemented

#### /api/rmap-initiate

**Specifications given:**
- Accepts base64(ASCII-armored PGP) as `payload`
- Decrypt with server private key → JSON `{"nonceClient": <u64>, "identity": "<GroupName>"}`
- Validate that `<GroupName>` has a public key present on disk.
- Reply (encrypted to the client’s public key) with JSON `{"nonceClient": <u64>, "nonceServer": <u64>}` as a base64(ASCII-armored PGP) `payload`

**Specifications given:**
- Accepts base64(ASCII-armored PGP) as `payload`
- Decrypt with server private key → JSON `{"nonceClient": <u64>, "identity": "<GroupName>"}`
- Validate that `<GroupName>` has a public key present on disk.
- Reply (encrypted to the client’s public key) with JSON `{"nonceClient": <u64>, "nonceServer": <u64>}` as a base64(ASCII-armored PGP) `payload`

#### /api/rmap-get-link

**Specifications given:**
- Accepts base64(ASCII-armored PGP) `payload`
- Decrypt → JSON `{"nonceServer": <u64>}`
- On success, create a watermarked PDF with your best technique, store a DB row, and return a JSON link made from the RMAP session secret (in this project: `<32-hex> = NonceClient || NonceServer`)

**What my code does:**
- Reads and decrypts payload with `im.decrypt_for_server(...)`
- Matches `nonceServer` to a pending session in `rmap.nonces` (prevents replay/garbage)
- Calls `final = rmap.handle_message2({"payload": payload})` → yields `{"result": "<32-hex>"}`  
- Looks up the source PDF by ID (`RMAP_SOURCE_DOC_ID`), resolves the storage path safely, and ensures the file exists
- Watermarks using the configured “best” method (`RMAP_METHOD`, e.g., BetterEOF) and server key (`RMAP_WM_KEY`)
- Saves the personalized PDF under `/watermarks/…__<Group>.pdf`
- Inserts a row into `Versions` with `link=<32-hex>` and the file path
- Returns `{"result":"<32-hex>"}`

##### Explanation of parameters:

- `-u` – server base URL
- `-i` – identity of the requesting group (must exist in /app/secrets/clients)
- `-s` – server public key path
- `-k` – client private key path
- `-p` – passphrase for client key
- `-o` – output path for resulting PDF

These endpoints will handle secure client-server exchanges using OpenGPG via PYGPy to protect document identifiers and nonces

#### Custom Watermarking (BetterEOF)

While thinking about how I could create a custom watermarking technique, I analyzed the weaknesses of the sample watermarking approach Toy-EOF, which suffered from:

- `Predictable data placement`
- `Lack of obfuscation`
- `No verification of ownership or document integrity`

**Approach (BetterEOF) summary:**
- **1.** It first reads the file and makes sure it starts with %PDF-. If not, it just stops right there since it isn’t a PDF file.
- **2.** Find the last %%EOF and insert it before it. All valid PDF files end with a %%EOF marker, which means inserting it after is generally a really bad idea since many tools like converters, antivirus software, or even proxies remove anything after EOF because it’s flagged as junk; therefore, BetterEOF inserts it before.
- **3.** It calculates a SHA256 hash of everything before the watermark — the head. This binds the watermark to that exact PDF file. If someone tries to change even just one byte, the hash will change, and the system will refuse to extract the watermark because the integrity check fails.
- **4.** A MAC (Message Authentication Code) is created over:
"wm2:v1:" + sha256(head) + nonce + ciphertext
Which means the authentication covers both the document’s head and the encrypted watermark content. In simple terms, the MAC proves that the watermark belongs exactly to this PDF and hasn’t been tampered with.
- **5.** The watermark payload (version, the head-hash, nonce, ciphertext, MAC, and so on) is put into a small JSON object using compact formatting, which is then base64url-encoded. The reason for this is because it keeps it short, predictable, and easy to parse.
- **6.** The watermark is written in two lines. Line one is a magic header, which is easy to find when searching inside a file. Line two, however, is the actual encrypted and authenticated watermark. So why two lines? This makes reading, writing, and even detecting the watermark very easy while keeping it resistant to corruption.


## 3. PHASE III – Testing, Coverage, and Security Hardening.
This phase focused on unit testing, coverage measurement, and addressing identified security issues.

Towards the end of phase two and the start of phase 3 a major security issue was exploited, which was because i forked the repo as opposed to cloning it. Due to this another group took advantage of this to find flag 1 and 2. This issue was quickly resolved by deleting the repo entirely and starting over from a private repo instead; this prevented others from reading future flags and learning how my watermarking worked.

I chose mutation testing as my specialization. I had previous exposure to software testing in my bachelor’s program, but it wasn’t very effective. This time, mutation testing proved far more valuable. In hindsight, it should have been run before increasing coverage to get a true baseline, but it worked out well in the end.

**Test Environment Setup**

```ini
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m pip install mutmut pytest-cov
```

**Test Environment Setup**

```ini
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
. .\.venv\Scripts\Activate.ps1
cd server
& .venv\Scripts\python.exe -m pytest -q
& .venv\Scripts\python.exe -m pytest --cov=src --cov-report=term-missing
```

#### Security Fixes
Also, during this phase, I became aware of a few major security issues in the code that I addressed, such as


**Issue 1**
- **Description:** Other users could read watermark secrets of documents they did not own.
- **Where:** server/src/server.py, function read_watermark
- **Severity:** Very High (cross-user data leakage)
- **Fix:** Enforce ownership in SQL lookups:

```ini
SELECT id, name, path FROM Documents
WHERE id = :id AND ownerid = :uid
```

- **Proof of Concept:** See Appendix A.


**Issue 1**
- **Description:** Flag file /app/flag was world-readable inside the container.
- **Where:** VRA container filesystem
- **Severity:** Medium
- **Fix:** Restrict file permissions and ownership:

```ini
docker compose exec server /bin/sh -lc \
  'chmod 600 /app/flag && chown root:root /app/flag && stat -c "%U %G %a %n" /app/flag'
```

**Issue 1**
- **Description:** Secrets directory on host was world-readable
- **Where:** /secrets/ on VRA host
- **Severity:** High
- **Fix:** Lock down permissions:

```ini
sudo chown -R root:root ./secrets
sudo chmod 755 ./secrets
sudo chmod 600 ./secrets/server_priv.asc
sudo chmod 644 ./secrets/server_pub.asc
sudo chown -R root:root ./secrets/clients
sudo chmod 755 ./secrets/clients
```

- **Proof of Concept:**

```ini
ls -ld ./secrets ./secrets/clients
drwxr-xr-x 3 root root 4096 Oct  8 21:46 ./secrets
drwxr-xr-x 2 root root 4096 Oct  9 18:57 ./secrets/clients

ls -l ./secrets | sed -n '1,50p'
total 12
drwxr-xr-x 2 root root 4096 Oct  9 18:57 clients
-rw------- 1 root root  878 Oct  8 21:46 server_priv.asc
-rw-r--r-- 1 root root  652 Oct  8 21:46 server_pub.asc
```