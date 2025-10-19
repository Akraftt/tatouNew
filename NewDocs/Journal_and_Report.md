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

### RMAP Endpoints Implemented


## 3. PHASE III – Testing, Coverage, and Security Hardening.