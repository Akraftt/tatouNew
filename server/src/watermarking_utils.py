""""watermarking_utils.py

Utility functions and registry for PDF watermarking methods.

This module exposes:

- :data:`METHODS`: a mapping from method name to an instantiated
  :class:`~watermarking_method.WatermarkingMethod`.
- :func:`explore_pdf`: build a lightweight JSON-serializable tree of PDF
  nodes with deterministic identifiers ("name nodes").
- :func:`apply_watermark`: run a concrete watermarking method on a PDF.
- :func:`read_watermark`: recover a secret using a concrete method.
- :func:`register_method` / :func:`get_method`: registry helpers.

Dependencies
------------
Only the standard library is required. If available, the exploration
routine will use *PyMuPDF* (``fitz``) for a richer object inventory. If
``fitz`` is not installed, it gracefully falls back to a permissive
regex-based scan for ``obj ... endobj`` blocks (this may miss compressed
object streams).

To enable the richer exploration, install PyMuPDF:

    pip install pymupdf

"""
from __future__ import annotations

from typing import Any, Dict, Final, Iterable, List, Mapping
import base64
import hashlib
import hmac
import io
import json
import os
import re

from watermarking_method import (
    PdfSource,
    WatermarkingMethod,
    load_pdf_bytes,
)
from add_after_eof import AddAfterEOF
from unsafe_bash_bridge_append_eof import UnsafeBashBridgeAppendEOF


# --------------------
# Anton EOF (hardened append-before-EOF with HMAC)
# --------------------

class AntonEOF(WatermarkingMethod):
    """Append a single signed marker line just before the final %%EOF.

    Line format (ASCII, single line):

        %ANTONWM <base64(secret)> <hex(hmac_sha256(secret,key))>

    - The *secret* is raw bytes (UTF-8 encoded) then Base64-encoded.
    - The tag is placed *before* the final ``%%EOF``. If ``%%EOF`` is
      missing (malformed PDF), we append both the tag and ``%%EOF``.
    - On read, the line is parsed and the HMAC validated with the
      provided *key*. If the HMAC does not match, a ValueError is raised.
    """

    name: str = "anton-eof"
    description: str = "Append signed Base64 tag before %%EOF (HMAC-SHA256)"

    _MARKER_PREFIX: Final[bytes] = b"%ANTONWM "

    def _sign(self, secret: str, key: str) -> str:
        mac = hmac.new(key.encode("utf-8"), secret.encode("utf-8"), hashlib.sha256)
        return mac.hexdigest()

    def _insert_before_eof(self, data: bytes, line: bytes) -> bytes:
        """Return new bytes with `line` inserted before the last %%EOF."""
        idx = data.rfind(b"%%EOF")
        if idx == -1:
            # No EOF marker: append our line and a proper EOF terminator.
            out = bytearray(data)
            if not out.endswith(b"\n"):
                out.extend(b"\n")
            out.extend(line)
            if not line.endswith(b"\n"):
                out.extend(b"\n")
            out.extend(b"%%EOF\n")
            return bytes(out)

        # Split at last %%EOF, keep any trailing whitespace after it.
        head = data[:idx]
        tail = data[idx:]  # starts with %%EOF
        # Ensure our line is separated by a newline.
        out = bytearray()
        out.extend(head)
        if not head.endswith(b"\n"):
            out.extend(b"\n")
        out.extend(line)
        if not line.endswith(b"\n"):
            out.extend(b"\n")
        out.extend(tail)
        return bytes(out)

    # --- WatermarkingMethod API ---

    def is_watermark_applicable(self, pdf: PdfSource, position: str | None = None) -> bool:
        # This method does not require a specific structure; any bytes starting with %PDF- are OK.
        try:
            data = load_pdf_bytes(pdf)
        except Exception:
            return False
        return data.startswith(b"%PDF-")

    def add_watermark(
        self,
        pdf: PdfSource,
        secret: str,
        key: str,
        position: str | None = None,
    ) -> bytes:
        data = load_pdf_bytes(pdf)

        # Build signed payload
        sig = self._sign(secret, key)
        b64 = base64.b64encode(secret.encode("utf-8")).decode("ascii")
        line = self._MARKER_PREFIX + f"{b64} {sig}".encode("ascii")

        return self._insert_before_eof(data, line)

    def read_secret(self, pdf: PdfSource, key: str) -> str:
        data = load_pdf_bytes(pdf)

        # Search tail region for the marker line (look in the last ~8 KiB)
        tail = data[-8192:] if len(data) > 8192 else data
        # Accept CRLF or LF line endings
        lines = tail.splitlines()

        # Walk from the end backward to find the most recent marker
        for raw in reversed(lines):
            if raw.startswith(self._MARKER_PREFIX):
                try:
                    payload = raw[len(self._MARKER_PREFIX):].strip().decode("ascii", "replace")
                    b64_part, sig = payload.split(" ", 1)
                    secret = base64.b64decode(b64_part.encode("ascii"), validate=True).decode("utf-8", "replace")
                except Exception as exc:
                    raise ValueError("anton-eof: invalid marker format") from exc

                # Verify HMAC
                expected = hmac.new(key.encode("utf-8"), secret.encode("utf-8"), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(sig, expected):
                    raise ValueError("anton-eof: HMAC verification failed")

                return secret

        raise ValueError("anton-eof: watermark not found")
    
    def get_usage(self) -> str:
        return "Embeds '%ANTONWM <base64(secret)> <hmac-hex>' just before %%EOF; HMAC key = provided key."


# --------------------
# New beter EOF
# --------------------
#
# --------------------

class BetterEOF(WatermarkingMethod):
    """
    Insert a signed+encrypted payload just before the final %%EOF.

    Marker:
        %WM2:v1
        <base64url(JSON)>

    Payload JSON (compact):
        {"v":1,"alg":"HMAC-SHA256","doc":"<sha256hex>","nonce":"<b64>","ct":"<b64>","mac":"<hex>"}

    - doc  = SHA256 of the PDF 'head' bytes (everything before the marker start)
    - nonce= 16 random bytes
    - ct   = secret XOR keystream(HMAC-SHA256) with (key, "wm2:enc:"+nonce+counter)
    - mac  = HMAC-SHA256(key, b"wm2:v1:" + doc_hash_bytes + nonce + ct)
    """

    name: str = "BetterEOF"
    _MAGIC_LINE: Final[bytes] = b"%WM2:v1\n"

    def _sha256(self, b: bytes) -> bytes:
        return hashlib.sha256(b).digest()

    def _b64u(self, b: bytes) -> str:
        return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")

    def _b64u_dec(self, s: str) -> bytes:
        # add padding back for urlsafe base64
        pad = "=" * ((4 - (len(s) % 4)) % 4)
        return base64.urlsafe_b64decode(s + pad)

    def _keystream(self, key: bytes, nonce: bytes, nbytes: int) -> bytes:
        """Generate nbytes of keystream using HMAC-SHA256 blocks."""
        out = bytearray()
        counter = 0
        while len(out) < nbytes:
            blk = hmac.new(key, b"wm2:enc:" + nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
            out.extend(blk)
            counter += 1
        return bytes(out[:nbytes])

    def _insert_before_eof(self, data: bytes, block: bytes) -> tuple[bytes, int]:
        """Insert block before the final %%EOF; return (new_bytes, head_len_before_block)."""
        idx = data.rfind(b"%%EOF")
        if idx == -1:
            # Treat end as EOF; append our block then %%EOF\n
            head = data
            if not head.endswith(b"\n"):
                head += b"\n"
            start = len(head)
            out = head + block + b"%%EOF\n"
            return out, start
        head = data[:idx]
        tail = data[idx:]  # starts with %%EOF
        if not head.endswith(b"\n"):
            head += b"\n"
        start = len(head)
        out = head + block + tail
        return out, start

    # --- WatermarkingMethod API ---

    def is_watermark_applicable(self, pdf: PdfSource, position: str | None = None) -> bool:
        try:
            data = load_pdf_bytes(pdf)
        except Exception:
            return False
        return data.startswith(b"%PDF-")

    def add_watermark(
        self,
        pdf: PdfSource,
        secret: str,
        key: str,
        position: str | None = None,
    ) -> bytes:
        if not isinstance(secret, str) or not secret:
            raise ValueError("secret must be a non-empty string")
        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")

        data = load_pdf_bytes(pdf)
        # Build encryption inputs
        nonce = os.urandom(16)
        sec_bytes = secret.encode("utf-8")
        ks = self._keystream(key.encode("utf-8"), nonce, len(sec_bytes))
        ct = bytes(a ^ b for a, b in zip(sec_bytes, ks))

        # Prepare doc binding and MAC
        # We will insert: MAGIC + b64url(JSON) + "\n"
        # Compute the head hash over bytes before the MAGIC start.
        # First, assemble a dummy block to measure start index:
        dummy_payload = b"{}"  # temporary; we only need placement to compute doc hash
        dummy_block = self._MAGIC_LINE + dummy_payload + b"\n"
        _, start = self._insert_before_eof(data, dummy_block)
        doc_hash = self._sha256(data[:start])

        mac = hmac.new(
            key.encode("utf-8"),
            b"wm2:v1:" + doc_hash + nonce + ct,
            hashlib.sha256,
        ).hexdigest()

        obj = {
            "v": 1,
            "alg": "HMAC-SHA256",
            "doc": doc_hash.hex(),
            "nonce": self._b64u(nonce),
            "ct": self._b64u(ct),
            "mac": mac,
        }
        j = json.dumps(obj, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        block = self._MAGIC_LINE + base64.urlsafe_b64encode(j) + b"\n"

        out, _ = self._insert_before_eof(data, block)
        return out

    def read_secret(self, pdf: PdfSource, key: str) -> str:
        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")

        data = load_pdf_bytes(pdf)
        # Find marker line near the end
        tail = data[-16384:] if len(data) > 16384 else data
        idx = tail.rfind(self._MAGIC_LINE)
        if idx == -1:
            raise ValueError("BetterEOFv1: marker not found")

        # Convert to absolute index in data
        abs_marker = len(data) - len(tail) + idx
        # Compute the head hash over bytes before marker start
        doc_hash = self._sha256(data[:abs_marker])

        # The payload line is immediately after MAGIC until next '\n'
        start = abs_marker + len(self._MAGIC_LINE)
        end = data.find(b"\n", start)
        if end == -1:
            end = len(data)
        b64_payload = data[start:end].strip()
        try:
            payload = json.loads(base64.urlsafe_b64decode(b64_payload))
            if not (isinstance(payload, dict) and payload.get("v") == 1 and payload.get("alg") == "HMAC-SHA256"):
                raise ValueError("BetterEOFv1: unsupported payload")
            doc_hex = str(payload["doc"])
            nonce = self._b64u_dec(str(payload["nonce"]))
            ct = self._b64u_dec(str(payload["ct"]))
            mac_hex = str(payload["mac"])
        except Exception as exc:
            raise ValueError("BetterEOFv1: malformed payload") from exc

        if doc_hex.lower() != doc_hash.hex():
            raise ValueError("BetterEOFv1: document binding failed")

        expected = hmac.new(
            key.encode("utf-8"),
            b"wm2:v1:" + bytes.fromhex(doc_hex) + nonce + ct,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(mac_hex, expected):
            raise ValueError("BetterEOFv1: MAC verification failed")

        # Decrypt
        ks = self._keystream(key.encode("utf-8"), nonce, len(ct))
        sec_bytes = bytes(a ^ b for a, b in zip(ct, ks))
        return sec_bytes.decode("utf-8")

    @staticmethod
    def get_usage() -> str:
        return (
            "Inserts '%WM2:v1\\n<base64url(JSON)>' just before %%EOF. "
            "Payload is encrypted (XOR+HMAC) and bound to the PDF via SHA256(head). "
            "Key is required to authenticate & decrypt."
        )

# --------------------
# Method registry
# --------------------

METHODS: Dict[str, WatermarkingMethod] = {
    AddAfterEOF.name: AddAfterEOF(),
    UnsafeBashBridgeAppendEOF.name: UnsafeBashBridgeAppendEOF(),
    AntonEOF.name: AntonEOF(),
    BetterEOF.name: BetterEOF(),
}
"""Registry of available watermarking methods.

Keys are human-readable method names (stable, lowercase, hyphenated)
exposed by each implementation's ``.name`` attribute. Values are
*instances* of the corresponding class.
"""


def register_method(method: WatermarkingMethod) -> None:
    """Register (or replace) a watermarking method instance by name."""
    METHODS[method.name] = method


def get_method(method: str | WatermarkingMethod) -> WatermarkingMethod:
    """Resolve a method from a string name or pass-through an instance.

    Raises
    ------
    KeyError
        If ``method`` is a string not present in :data:`METHODS`.
    """
    if isinstance(method, WatermarkingMethod):
        return method
    try:
        return METHODS[method]
    except KeyError as exc:
        raise KeyError(
            f"Unknown watermarking method: {method!r}. Known: {sorted(METHODS)}"
        ) from exc


# --------------------
# Public API helpers
# --------------------

def apply_watermark(
    method: str | WatermarkingMethod,
    pdf: PdfSource,
    secret: str,
    key: str,
    position: str | None = None,
) -> bytes:
    """Apply a watermark using the specified method and return new PDF bytes."""
    m = get_method(method)
    return m.add_watermark(pdf=pdf, secret=secret, key=key, position=position)

def is_watermarking_applicable(
    method: str | WatermarkingMethod,
    pdf: PdfSource,
    position: str | None = None,
) -> bool:
    """Check if a method can apply a watermark to this PDF."""
    m = get_method(method)
    return m.is_watermark_applicable(pdf=pdf, position=position)


def read_watermark(method: str | WatermarkingMethod, pdf: PdfSource, key: str) -> str:
    """Recover a secret from ``pdf`` using the specified method."""
    m = get_method(method)
    return m.read_secret(pdf=pdf, key=key)


# --------------------
# PDF exploration
# --------------------

# Pre-compiled regex for the fallback parser (very permissive):
_OBJ_RE: Final[re.Pattern[bytes]] = re.compile(
    rb"(?m)^(\d+)\s+(\d+)\s+obj\b"
)
_ENDOBJ_RE: Final[re.Pattern[bytes]] = re.compile(rb"\bendobj\b")
_TYPE_RE: Final[re.Pattern[bytes]] = re.compile(rb"/Type\s*/([A-Za-z]+)")


def _sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def explore_pdf(pdf: PdfSource) -> Dict[str, Any]:
    """Return a JSON-serializable *tree* describing the PDF's nodes.

    The structure is deterministic for a given set of input bytes. When
    PyMuPDF (``fitz``) is available, the function uses the cross
    reference (xref) table to enumerate objects and page nodes. When not
    available, it falls back to scanning for ``obj`` / ``endobj`` blocks.

    The returned dictionary has the following shape (fields may be
    omitted when data is unavailable):

    .. code-block:: json

        {
          "id": "pdf:<sha1>",
          "type": "Document",
          "size": 12345,
          "children": [
            {"id": "page:0000", "type": "Page", ...},
            {"id": "obj:000001", "type": "XObject", ...}
          ]
        }

    Each node includes a deterministic ``id`` suitable as a "name node".
    """
    data = load_pdf_bytes(pdf)

    root: Dict[str, Any] = {
        "id": f"pdf:{_sha1(data)}",
        "type": "Document",
        "size": len(data),
        "children": [],
    }

    try:
        import fitz  # type: ignore

        doc = fitz.open(stream=data, filetype="pdf")
        # Pages as first-class nodes
        for page_index in range(doc.page_count):
            node = {
                "id": f"page:{page_index:04d}",
                "type": "Page",
                "index": page_index,
                "bbox": list(doc.load_page(page_index).bound()),  # [x0,y0,x1,y1]
            }
            root["children"].append(node)

        # XRef objects
        xref_len = doc.xref_length()
        for xref in range(1, xref_len):
            try:
                s = doc.xref_object(xref, compressed=False) or ""
            except Exception:
                s = ""
            s_bytes = s.encode("latin-1", "replace") if isinstance(s, str) else b""
            # Type detection
            m = _TYPE_RE.search(s_bytes)
            pdf_type = m.group(1).decode("ascii", "replace") if m else "Object"
            node = {
                "id": f"obj:{xref:06d}",
                "type": pdf_type,
                "xref": xref,
                "is_stream": bool(doc.xref_is_stream(xref)),
                "content_sha1": _sha1(s_bytes) if s_bytes else None,
            }
            root["children"].append(node)

        doc.close()
        return root
    except Exception:
        pass

    # Regex fallback: enumerate uncompressed objects
    children: List[Dict[str, Any]] = []
    for m in _OBJ_RE.finditer(data):
        obj_num = int(m.group(1))
        gen_num = int(m.group(2))
        start = m.end()
        end_match = _ENDOBJ_RE.search(data, start)
        end = end_match.start() if end_match else start
        slice_bytes = data[start:end]
        # Guess type
        t = _TYPE_RE.search(slice_bytes)
        pdf_type = t.group(1).decode("ascii", "replace") if t else "Object"
        node = {
            "id": f"obj:{obj_num:06d}:{gen_num:05d}",
            "type": pdf_type,
            "object": obj_num,
            "generation": gen_num,
            "content_sha1": _sha1(slice_bytes),
        }
        children.append(node)

    # Also derive simple page nodes by searching for '/Type /Page'
    page_nodes = [c for c in children if c.get("type") == "Page"]
    for i, c in enumerate(page_nodes):
        # Provide deterministic page IDs independent from object numbers
        c_page = {
            "id": f"page:{i:04d}",
            "type": "Page",
            "xref_hint": c["id"],
        }
        children.insert(i, c_page)

    root["children"] = children
    return root






__all__ = [
    "METHODS",
    "register_method",
    "get_method",
    "apply_watermark",
    "read_watermark",
    "explore_pdf",
    "is_watermarking_applicable",
]
