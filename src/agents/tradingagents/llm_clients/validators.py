"""Model name validators for each provider."""


def validate_model(provider: str, model: str) -> bool:
    """Check if model name is valid for the given provider.

    All providers accept any model identifier; validation is left to the
    provider endpoint at request time.
    """
    return bool(model and model.strip())
