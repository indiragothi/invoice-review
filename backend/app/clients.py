"""Fixed list of the CA firm's clients (fictional).

Every upload is tagged with one of these. The buyer GSTIN on a purchase invoice must match the
client's GSTIN (`BUYER_NOT_CLIENT`). Adding a client is a code change; there is no client CRUD.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Client:
    id: str
    name: str
    gstin: str
    state_code: str
    city: str


CLIENTS: tuple[Client, ...] = (
    Client(
        id="C001",
        name="Shree Ganesh Traders",
        gstin="23QXGPS4821K1ZU",
        state_code="23",
        city="Indore, Madhya Pradesh",
    ),
    Client(
        id="C002",
        name="Annapurna Restaurant Pvt Ltd",
        gstin="27QWRCA7310M1ZK",
        state_code="27",
        city="Pune, Maharashtra",
    ),
    Client(
        id="C003",
        name="Kaveri Dental Clinic",
        gstin="29QKDPK5274H1ZH",
        state_code="29",
        city="Bengaluru, Karnataka",
    ),
)

CLIENTS_BY_ID: dict[str, Client] = {client.id: client for client in CLIENTS}
