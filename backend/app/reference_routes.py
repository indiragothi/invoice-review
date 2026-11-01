"""Read-only lists the UI needs: the fixed clients and the fixed ledger catalog."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.accounting.catalog import LEDGERS
from app.clients import CLIENTS

router = APIRouter(prefix="/api", tags=["reference"])


class ClientResponse(BaseModel):
    id: str
    name: str
    gstin: str
    state_code: str
    city: str


class LedgerResponse(BaseModel):
    code: str
    name: str
    typical: str


@router.get("/clients", response_model=list[ClientResponse])
def list_clients():
    return [ClientResponse(**vars(client)) for client in CLIENTS]


@router.get("/accounting/ledgers", response_model=list[LedgerResponse])
def list_ledgers():
    return [LedgerResponse(**vars(ledger)) for ledger in LEDGERS]
