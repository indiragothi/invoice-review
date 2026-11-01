"""Correction-email models. The app drafts text; it has no code that sends email."""

from pydantic import BaseModel, Field


class EmailDraft(BaseModel):
    """What the model must return."""

    subject: str = Field(description="A short subject line that names the invoice number.")
    body: str = Field(description="The plain-text email body, ready to copy.")


class CorrectionEmailResponse(BaseModel):
    subject: str
    body: str
    issue_codes: list[str]  # the eligible issues the draft is about
