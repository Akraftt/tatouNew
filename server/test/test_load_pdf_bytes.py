import io
import os
import pytest
from pathlib import Path
from watermarking_method import load_pdf_bytes, is_pdf_bytes


def _minimal_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
    # tiny "fake" pdf that will be used for testing purposes

# returns true when data start with a pdf header
def test_is_pdf_bytes_true_for_valid_header():
    # Arrange - call the "fake" pdf
    data = _minimal_pdf_bytes()
    # Act
    ok = is_pdf_bytes(data)
    # Assert
    assert ok is True

# opposite of the previous test 
def test_is_pdf_bytes_false_for_non_pdf():
    # Arrange
    data = b"not a pdf"
    # Act
    ok = is_pdf_bytes(data)
    # Assert
    assert ok is False

# tests raw bytes and returns if they seems to be a pdf
def test_load_pdf_bytes_from_bytes_ok():
    # Arrange
    data = _minimal_pdf_bytes()
    # Act
    out = load_pdf_bytes(data)
    # Assert
    assert out.startswith(b"%PDF-")
    assert out.endswith(b"%%EOF\n")


def test_load_pdf_bytes_from_path_ok(tmp_path: Path):
    # Arrange - write "fake" pdf to a temp file
    p = tmp_path / "doc.pdf"
    p.write_bytes(_minimal_pdf_bytes())
    # Act
    out = load_pdf_bytes(str(p)) 
    # Assert, same as previous also.
    assert out.startswith(b"%PDF-")
    assert out.endswith(b"%%EOF\n")

# see if it accepts an open binary file
def test_load_pdf_bytes_from_file_object_ok(tmp_path: Path):
    # Arrange, first 2 same as previous
    p = tmp_path / "doc.pdf"
    p.write_bytes(_minimal_pdf_bytes())
    f = p.open("rb") # new to open
    try:
        # Act
        out = load_pdf_bytes(f)
    finally:
        f.close()
    # Assert
    assert out.startswith(b"%PDF-")
    assert out.endswith(b"%%EOF\n")

# path that dosnt exist
def test_load_pdf_bytes_raises_on_missing_file(tmp_path: Path):
    # Arrange
    p = tmp_path / "missing.pdf"
    # Act & Assert
    with pytest.raises(FileNotFoundError):
        load_pdf_bytes(p.as_posix())

# 
def test_load_pdf_bytes_raises_on_non_pdf_bytes():
    # Arrange
    notPDF = b"this isnt a pdf"
    #Act & Assert
    with pytest.raises(ValueError):
        load_pdf_bytes(notPDF)

# bad and unsupported input
def test_load_pdf_bytes_raises_on_unsupported_source_type():
    # Arrange
    class oddInput: 
        pass
    # Act / Assert
    with pytest.raises(TypeError):
        load_pdf_bytes(oddInput())