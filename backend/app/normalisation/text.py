"""Small text clean-ups."""


def clean_text(text: str | None) -> str | None:
    """Collapse runs of whitespace; empty becomes None."""
    if text is None:
        return None
    cleaned = " ".join(text.split())
    return cleaned or None


def normalise_gstin(text: str | None) -> str | None:
    """Remove spaces and upper-case. Whether it is valid is the validator's job."""
    if text is None:
        return None
    cleaned = "".join(text.split()).upper()
    return cleaned or None
