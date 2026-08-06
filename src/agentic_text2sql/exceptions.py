"""Stable, user-safe project exceptions."""


class Text2SQLError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(Text2SQLError):
    """Raised when local configuration is invalid."""


class ProviderUnavailableError(Text2SQLError):
    """Raised when a local model provider cannot be reached."""


class StructuredOutputError(Text2SQLError):
    """Raised when a provider response violates its declared contract."""
