import pytest
import watermarking_utils as WM

# retrive the valid methods
def test_get_method_known_names_exist():
    # Arrange / Act
    names = set(WM.METHODS.keys())
    # Assert
    assert "anton-eof" in names
    assert "toy-eof" in names

# try to retrive methods that dostn exsit at all
def test_get_method_unknown_raises_keyerror():
    # Arrange
    unknown = "what is this"
    # Act / Assert
    with pytest.raises(KeyError):
        WM.get_method(unknown)