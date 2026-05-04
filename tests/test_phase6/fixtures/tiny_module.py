"""Test fixture for the AST chunker. DO NOT IMPORT — code is read as text."""
GLOBAL_CONST = 42


def first_function(x: int) -> int:
    """Adds one."""
    return x + 1


def second_function(y: int) -> int:
    """Adds two."""
    inner = y + 2
    return inner
