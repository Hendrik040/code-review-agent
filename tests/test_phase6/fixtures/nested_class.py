"""Test fixture: nested class with methods. Read as text, not imported."""


class OuterClass:
    """Top-level class with a couple of methods."""

    CLASS_CONST = "hello"

    def method_one(self, value: int) -> int:
        """First method."""
        return value * 2

    def method_two(self, items: list[int]) -> int:
        """Second method, multi-line."""
        total = 0
        for item in items:
            total += item
        return total
