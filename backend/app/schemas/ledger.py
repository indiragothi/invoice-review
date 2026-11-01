"""Ledger suggestion models."""

from pydantic import BaseModel, Field


class LedgerChoice(BaseModel):
    """What the model must return: one catalog code and a one-line reason."""

    code: str = Field(description="One ledger code copied from the catalog, e.g. 6130.")
    reason: str = Field(description="One short sentence on why, based on the vendor and items.")


class LedgerSuggestion(BaseModel):
    """A suggestion after the code check. `suggested_code` is None when the model's code was not
    in the catalog; the reviewer then picks one by hand."""

    suggested_code: str | None
    reason: str
