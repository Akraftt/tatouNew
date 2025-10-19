from __future__ import annotations
import json
from pathlib import Path
import io
import sys
import builtins
import types
import pytest
import watermarking_cli as cli
import argparse
from watermarking_method import load_pdf_bytes
from rmap_service import register_rmap_routes




# create a minimal pdf in a temp folder
def _mk_min_pdf(tmp_path: Path, name: str = "in.pdf") -> Path:
    p = tmp_path / name
    p.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        b"%%EOF\n"
    )
    return p

# verify that the cli can list what watermarking method are avaliable
# this is basically just a test that it can find anton-eof, if this dosnt work nothing will.
def test_methods_lists_registry_and_exits_zero(capsys):
    code = cli.main(["methods"])
    out = capsys.readouterr().out
    assert "anton-eof" in out
    assert "toy-eof" in out
    assert code == 0


# explores the small temp pdf we create earlier and see if the output is in valid json format
def test_explore_tempPDF_json(tmp_path, capsys):
    inp = _mk_min_pdf(tmp_path)
    code = cli.main(["explore", str(inp)])
    captured = capsys.readouterr().out
    doc = json.loads(captured)
    assert code == 0
    assert doc["type"] == "Document"
    assert isinstance(doc["size"], int)


# embed a secret using the anton-eof into the temp PDF then extract it
# core funtioncality test, if this dosnt work neither will anything
def test_embed_and_extract(tmp_path, capsys):
    inp = _mk_min_pdf(tmp_path)
    outp = tmp_path / "out.pdf"

    # embed part
    code1 = cli.main([
        "embed",
        str(inp),
        str(outp),
        "--method", "anton-eof",
        "--key", "k",
        "--secret", "s"
    ])
    assert code1 == 0
    assert outp.exists()
    assert outp.read_bytes().startswith(b"%PDF-")

    capsys.readouterr()

    # extract part
    code2 = cli.main([
        "extract",
        str(outp),
        "--method", "anton-eof",
        "--key", "k"
    ])
    captured = capsys.readouterr().out.strip()
    assert code2 == 0
    assert captured == "s"


# edge case test that tries to embed into a none PDF, expected to fail (good)
def test_embed_not_applicable_on_non_pdf(tmp_path, capsys):
    txt = tmp_path / "note.txt"
    txt.write_text("hello")
    outp = tmp_path / "ignored.pdf"
    code = cli.main([
        "embed",
        str(txt),
        str(outp),
        "--method", "anton-eof",
        "--key", "k",
        "--secret", "s"
    ])
    assert code == 5
    msg = capsys.readouterr().out
    assert "not applicable" in msg


# edge case test that embeds with (A-ket) using toy-eof then extracts (B-key)
# Basically testing with an invalid key (expected to fail)
def test_extract_wrong_key_returns_exit4(tmp_path, capsys):
    inp = _mk_min_pdf(tmp_path)
    outp = tmp_path / "w.pdf"

    # embed with toy-eof using key A
    code1 = cli.main([
        "embed",
        str(inp),
        str(outp),
        "--method", "toy-eof",
        "--key", "A",
        "--secret", "flag"
    ])
    assert code1 == 0

    # extract with key B
    code2 = cli.main([
        "extract",
        str(outp),
        "--method", "toy-eof",
        "--key", "B",
    ])
    assert code2 == 4

# new test for methods that also includes betterEOF, could have updated the old one but need pratice making tests
def test_methods_also_lists_betterEOF(capsys):
    # Arrange and act
    code = cli.main(["methods"])
    out = capsys.readouterr().out
    # Assert
    assert code == 0
    assert "BetterEOF" in out 

# calls explore on a file that dosnt exist
def test_explore_missing_file(capsys, tmp_path):
    missing = tmp_path / "NotaPDF.pdf"
    code = cli.main(["explore", str(missing)])
    assert code != 0

# tries to run embed with a unkown/made up method nae
def test_embed_unknown_method(tmp_path):
    inp = _mk_min_pdf(tmp_path)
    outp = tmp_path / "out.pdf"
    with pytest.raises(KeyError):
        cli.main([
            "embed", str(inp), str(outp),
            "--method", "no-such-method",
            "--key", "k",
            "--secret", "s",
        ])

# runs extract on the miimal pdf with the watermarking method ive done with no secret
def test_extract_on_pdf_without_secret(tmp_path, capsys):
    inp = _mk_min_pdf(tmp_path)
    code = cli.main([
        "extract", str(inp),
        "--method", "anton-eof",
        "--key", "k",
    ])
    assert code != 0


# basically a full blown tests that embeds secret then extract
# this should suceed and match 
def test_embed_and_extract_bettereof(tmp_path, capsys):
    # Arrange
    inp = _mk_min_pdf(tmp_path)
    outp = tmp_path / "outbetter.pdf"

    # Act
    c1 = cli.main([
        "embed", str(inp), str(outp),
        "--method", "BetterEOF",
        "--key", "course-demo-key",
        "--secret", "hello",
    ])
    # Assert 
    assert c1 == 0 and outp.exists()
    capsys.readouterr()

    # Act
    c2 = cli.main([
        "extract", str(outp),
        "--method", "BetterEOF",
        "--key", "course-demo-key",
    ])
    out = capsys.readouterr().out.strip()

    # Assert
    assert c2 == 0
    assert out == "hello"


def test_resolve_key_from_file(tmp_path):
    f = tmp_path / "key.txt"
    f.write_text("abc123\n")
    args = types.SimpleNamespace(key=None, key_file=str(f), key_stdin=False)
    assert cli._resolve_key(args) == "abc123"

def test_invalid_pdf_error_message():
    with pytest.raises(ValueError, match="%PDF"):
        load_pdf_bytes(b"not a pdf")

def test_rmap_env_passphrase_required(monkeypatch):
    monkeypatch.delenv("RMAP_SERVER_PRIV_PASSPHRASE", raising=False)
    with pytest.raises(KeyError):
        register_rmap_routes()