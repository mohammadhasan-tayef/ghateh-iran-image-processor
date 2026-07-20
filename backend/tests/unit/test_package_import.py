"""Packaging smoke tests."""

from importlib import import_module


def test_installed_package_can_be_imported() -> None:
    """The installed src-layout package imports without runtime services."""
    package = import_module("ghateh_processor")

    assert package.__package__ == "ghateh_processor"
