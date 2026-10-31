"""Generate the synthetic GST sample corpus and its ground-truth manifest together.

Every document is fictional. Files go to `samples/generated/` and the expected values to
`samples/manifest.json`, written in the same run so ground truth cannot drift from the files.

Run from backend/:

    uv run --locked --no-sync python -m scripts.generate_samples
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Literal

import pymupdf
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from stdnum import luhn
from stdnum.in_ import gstin as gstin_lib

from app.clients import CLIENTS_BY_ID
from app.config import APP_CONFIG

OUT_DIR = APP_CONFIG.samples_dir / "generated"
MANIFEST_PATH = APP_CONFIG.samples_dir / "manifest.json"
TODAY = date(2026, 10, 31)

STATE_NAMES = {
    "23": "Madhya Pradesh",
    "27": "Maharashtra",
    "29": "Karnataka",
}

CENT = Decimal("0.01")


# ---------------------------------------------------------------- money and text helpers


def q2(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def inr(value: Decimal) -> str:
    """Indian digit grouping: 123456.5 -> 1,23,456.50."""
    sign = "-" if value < 0 else ""
    whole, fraction = f"{abs(q2(value)):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    return f"{sign}{whole}.{fraction}"


_ONES = (
    "Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen "
    "Fifteen Sixteen Seventeen Eighteen Nineteen"
).split()
_TENS = "_ _ Twenty Thirty Forty Fifty Sixty Seventy Eighty Ninety".split()


def _below_hundred(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f" {_ONES[ones]}" if ones else "")


def _below_thousand(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = []
    if hundreds:
        parts.append(f"{_ONES[hundreds]} Hundred")
    if rest:
        parts.append(_below_hundred(rest))
    return " ".join(parts)


def rupees_in_words(amount: Decimal) -> str:
    """Indian numbering (lakh, crore) for a whole-rupee amount."""
    n = int(amount)
    if n == 0:
        return "Rupees Zero Only"
    parts = []
    for size, name in ((10_000_000, "Crore"), (100_000, "Lakh"), (1_000, "Thousand")):
        count, n = divmod(n, size)
        if count:
            parts.append(f"{_below_thousand(count)} {name}")
    if n:
        parts.append(_below_thousand(n))
    return "Rupees " + " ".join(parts) + " Only"


def make_gstin(state_code: str, pan: str) -> str:
    base = f"{state_code}{pan}1Z"
    return base + luhn.calc_check_digit(base, gstin_lib._ALPHABET)


def corrupt_gstin(valid: str) -> str:
    """Change the check character so the checksum fails (a realistic typo)."""
    alphabet = gstin_lib._ALPHABET
    replacement = alphabet[(alphabet.index(valid[-1]) + 7) % len(alphabet)]
    return valid[:-1] + replacement


def format_date(value: date, style: str) -> str:
    if style == "dd-mm-yyyy":
        return value.strftime("%d-%m-%Y")
    if style == "dd/mm/yyyy":
        return value.strftime("%d/%m/%Y")
    return value.strftime("%d %b %Y")


# ---------------------------------------------------------------- data model


@dataclass(frozen=True)
class Party:
    name: str
    address: tuple[str, ...]
    state_code: str
    gstin: str | None


@dataclass(frozen=True)
class Item:
    description: str
    hsn_sac: str
    quantity: Decimal
    unit: str
    rate: Decimal
    gst_rate: Decimal

    @property
    def amount(self) -> Decimal:
        return q2(self.quantity * self.rate)


@dataclass
class Bill:
    number: int
    slug: str
    kind: Literal["invoice", "receipt"]
    scenario: str
    split: Literal["dev", "test"]
    client_id: str
    vendor: Party
    buyer: Party | None
    invoice_number: str
    invoice_date: date
    date_style: str
    items: list[Item]
    expected_ledger: str
    expected_errors: list[str] = field(default_factory=list)
    charge_igst: bool | None = None  # None: decide from vendor state vs place of supply
    layout: Literal["classic", "compact"] = "classic"
    output: Literal["pdf", "scan", "photo"] = "pdf"
    printed_total_delta: Decimal = Decimal("0")
    show_tax: bool = True
    receipt_time: str | None = None

    # ---- derived values

    @property
    def place_of_supply(self) -> str:
        return self.buyer.state_code if self.buyer else self.vendor.state_code

    @property
    def is_igst(self) -> bool:
        if self.charge_igst is not None:
            return self.charge_igst
        return self.vendor.state_code != self.place_of_supply

    @property
    def taxable_value(self) -> Decimal:
        return sum((item.amount for item in self.items), Decimal("0"))

    def tax_lines(self) -> list[tuple[str, Decimal, Decimal]]:
        """(label, rate, amount) per tax head and GST rate."""
        if not self.show_tax:
            return []
        by_rate: dict[Decimal, Decimal] = {}
        for item in self.items:
            by_rate[item.gst_rate] = by_rate.get(item.gst_rate, Decimal("0")) + item.amount
        lines = []
        for rate, base in sorted(by_rate.items()):
            if self.is_igst:
                lines.append(("IGST", rate, q2(base * rate / 100)))
            else:
                half = rate / 2
                lines.append(("CGST", half, q2(base * half / 100)))
                lines.append(("SGST", half, q2(base * half / 100)))
        return lines

    def tax_total(self, head: str) -> Decimal:
        return sum((amt for label, _, amt in self.tax_lines() if label == head), Decimal("0"))

    @property
    def exact_total(self) -> Decimal:
        return self.taxable_value + sum((amt for _, _, amt in self.tax_lines()), Decimal("0"))

    @property
    def correct_total(self) -> Decimal:
        return self.exact_total.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    @property
    def round_off(self) -> Decimal:
        return self.correct_total - self.exact_total

    @property
    def printed_total(self) -> Decimal:
        return self.correct_total + self.printed_total_delta

    @property
    def filename(self) -> str:
        extension = {"pdf": "pdf", "scan": "png", "photo": "jpg"}[self.output]
        return f"{self.number:02d}-{self.slug}.{extension}"


# ---------------------------------------------------------------- the corpus

V_STATIONERY = Party(
    "Sai Stationery Mart",
    ("14, Siyaganj Main Road", "Indore - 452007"),
    "23",
    make_gstin("23", "QSSPM6142B"),
)
V_GRAINS = Party(
    "Bharat Wholesale Grains",
    ("Shop 7, Chhawni Anaj Mandi", "Indore - 452001"),
    "23",
    make_gstin("23", "QBWFG7451A"),
)
V_TECH = Party(
    "TechNova Systems Pvt Ltd",
    ("402, Kamala Mills Compound", "Lower Parel, Mumbai - 400013"),
    "27",
    make_gstin("27", "QTNCS8025R"),
)
V_CONSULT = Party(
    "Sahyadri Consultants LLP",
    ("3rd Floor, Prabhat Road", "Pune - 411004"),
    "27",
    make_gstin("27", "QSCFC4718D"),
)
V_REPAIR = Party(
    "Malwa Repair Works",
    ("22, Palasia Square", "Indore - 452001"),
    "23",
    corrupt_gstin(make_gstin("23", "QMRPW2963E")),
)
V_AGRO = Party(
    "Narmada Agro Distributors",
    ("Plot 9, Sanwer Road Industrial Area", "Indore - 452015"),
    "23",
    make_gstin("23", "QNAFD3391L"),
)
V_BROADBAND = Party(
    "Netlink Broadband Services Pvt Ltd",
    ("5th Floor, Vijay Nagar Square", "Indore - 452010"),
    "23",
    make_gstin("23", "QNBCB1187P"),
)
V_PROPERTY = Party(
    "Rajwada Properties",
    ("101, MG Road", "Indore - 452001"),
    "23",
    make_gstin("23", "QRPFR5530T"),
)
V_KIRANA = Party(
    "Shubh Laxmi Kirana Wholesale",
    ("31, Malharganj", "Indore - 452002"),
    "23",
    make_gstin("23", "QSLFK9064G"),
)
V_PRINTERS = Party(
    "Prakash Printers",
    ("12, Narayan Peth", "Pune - 411030"),
    "27",
    make_gstin("27", "QPPPP3378N"),
)
V_FUEL = Party(
    "Narmada Fuel Station",
    ("AB Road, Rau", "Indore - 453331"),
    "23",
    make_gstin("23", "QNFFS1408C"),
)
V_RESTAURANT = Party(
    "Hotel Swad Sagar",
    ("Sarafa Bazaar", "Indore - 452002"),
    "23",
    make_gstin("23", "QHSFS6629Q"),
)
OTHER_BUYER = Party(
    "Ganesh Trading Company",
    ("8, Jawahar Marg", "Indore - 452002"),
    "23",
    make_gstin("23", "QGTFC2244J"),
)


def client_party(client_id: str) -> Party:
    client = CLIENTS_BY_ID[client_id]
    return Party(client.name, (client.city,), client.state_code, client.gstin)


def d(value: str) -> Decimal:
    return Decimal(value)


def kirana_items() -> list[Item]:
    rng = random.Random(9)
    goods = [
        ("Sunflower oil 1 L pouch", "1512", "5", "pcs", "145"),
        ("Toor dal 1 kg", "0713", "5", "kg", "128"),
        ("Moong dal 1 kg", "0713", "5", "kg", "118"),
        ("Chana dal 1 kg", "0713", "5", "kg", "92"),
        ("Sugar 1 kg", "1701", "5", "kg", "46"),
        ("Poha 1 kg", "1904", "5", "kg", "58"),
        ("Rava 1 kg", "1103", "5", "kg", "52"),
        ("Besan 1 kg", "1106", "5", "kg", "96"),
        ("Tea 500 g", "0902", "5", "pcs", "245"),
        ("Coffee 200 g jar", "2101", "5", "pcs", "310"),
        ("Turmeric powder 200 g", "0910", "5", "pcs", "54"),
        ("Red chilli powder 200 g", "0904", "5", "pcs", "68"),
        ("Coriander powder 200 g", "0909", "5", "pcs", "44"),
        ("Cumin seeds 100 g", "0909", "5", "pcs", "62"),
        ("Mustard seeds 100 g", "1207", "5", "pcs", "18"),
        ("Iodised salt 1 kg", "2501", "5", "kg", "24"),
        ("Rice bran oil 1 L", "1515", "5", "pcs", "152"),
        ("Basmati rice 5 kg", "1006", "5", "pcs", "560"),
        ("Wheat atta 10 kg", "1101", "5", "pcs", "420"),
        ("Biscuits family pack", "1905", "5", "pcs", "35"),
        ("Instant noodles 12-pack", "1902", "5", "pcs", "168"),
        ("Bath soap 4-pack", "3401", "18", "pcs", "112"),
        ("Detergent powder 1 kg", "3402", "18", "kg", "98"),
        ("Dishwash bar 3-pack", "3402", "18", "pcs", "45"),
        ("Toothpaste 150 g", "3306", "18", "pcs", "92"),
        ("Shampoo 340 ml", "3305", "18", "pcs", "199"),
        ("Hair oil 300 ml", "3305", "18", "pcs", "145"),
        ("Floor cleaner 1 L", "3402", "18", "pcs", "165"),
        ("Mosquito coil 10-pack", "3808", "18", "pcs", "38"),
        ("Matchbox carton (10)", "3605", "18", "pcs", "20"),
        ("Agarbatti 100 sticks", "3307", "5", "pcs", "55"),
        ("Tomato ketchup 1 kg", "2103", "5", "pcs", "135"),
        ("Pickle 500 g", "2001", "5", "pcs", "110"),
        ("Papad 200 g", "1905", "5", "pcs", "48"),
    ]
    return [
        Item(desc, hsn, Decimal(rng.choice([6, 10, 12, 20, 24, 30])), unit, d(rate), d(gst))
        for desc, hsn, gst, unit, rate in goods
    ]


def build_corpus() -> list[Bill]:
    c001 = client_party("C001")
    c002 = client_party("C002")
    c003 = client_party("C003")
    return [
        Bill(
            1, "intra-classic", "invoice", "happy_intra_state", "dev", "C001",
            V_STATIONERY, c001, "SSM/26-27/0412", date(2026, 8, 14), "dd-mm-yyyy",
            [
                Item("A4 copier paper 75 GSM", "4802", d("20"), "ream", d("245"), d("18")),
                Item("Ball pens (box of 10)", "9608", d("15"), "box", d("90"), d("18")),
                Item("Box files", "4820", d("25"), "pcs", d("65"), d("18")),
            ],
            expected_ledger="6150",
        ),
        Bill(
            2, "intra-compact", "invoice", "happy_intra_state", "test", "C001",
            V_GRAINS, c001, "BWG/2627/1186", date(2026, 9, 17), "dd/mm/yyyy",
            [
                Item("Basmati rice 25 kg bag", "1006", d("40"), "bag", d("1850"), d("5")),
                Item("Toor dal 30 kg bag", "0713", d("10"), "bag", d("3600"), d("5")),
            ],
            expected_ledger="5100",
            layout="compact",
        ),
        Bill(
            3, "inter-classic", "invoice", "happy_inter_state", "dev", "C001",
            V_TECH, c001, "TN/MH/26-27/0091", date(2026, 8, 21), "dd mon yyyy",
            [
                Item("Laptop i5 16 GB / 512 GB SSD", "8471", d("2"), "pcs", d("52500"), d("18")),
                Item("Monochrome laser printer", "8443", d("1"), "pcs", d("14800"), d("18")),
            ],
            expected_ledger="1500",
        ),
        Bill(
            4, "inter-compact", "invoice", "happy_inter_state", "test", "C003",
            V_CONSULT, c003, "SC-LLP/2026/047", date(2026, 10, 5), "dd mon yyyy",
            [
                Item("Practice management consulting", "998311", d("1"), "job", d("45000"),
                     d("18")),
                Item("Front-desk staff training workshop", "999293", d("1"), "job", d("12000"),
                     d("18")),
            ],
            expected_ledger="6160",
            layout="compact",
        ),
        Bill(
            5, "invalid-vendor-gstin", "invoice", "invalid_vendor_gstin", "dev", "C001",
            V_REPAIR, c001, "MRW/26-27/233", date(2026, 9, 23), "dd-mm-yyyy",
            [
                Item("Split AC servicing", "998719", d("3"), "unit", d("1500"), d("18")),
                Item("Compressor gas refill", "998719", d("1"), "job", d("3200"), d("18")),
            ],
            expected_ledger="6140",
            expected_errors=["invalid_vendor_gstin"],
        ),
        Bill(
            6, "total-mismatch", "invoice", "total_mismatch", "test", "C001",
            V_AGRO, c001, "NAD/26-27/0758", date(2026, 10, 14), "dd/mm/yyyy",
            [
                Item("Sugar 50 kg bag", "1701", d("20"), "bag", d("2150"), d("5")),
                Item("Groundnut oil 15 L tin", "1508", d("12"), "tin", d("2380"), d("5")),
            ],
            expected_ledger="5100",
            expected_errors=["total_mismatch"],
            layout="compact",
            printed_total_delta=d("1000"),
        ),
        Bill(
            7, "wrong-tax-split", "invoice", "tax_split_inconsistent", "dev", "C001",
            V_BROADBAND, c001, "NLB/OCT26/45821", date(2026, 10, 18), "dd-mm-yyyy",
            [
                Item("Broadband 100 Mbps plan, Oct 2026", "998422", d("1"), "month", d("999"),
                     d("18")),
                Item("Static IP rental, Oct 2026", "998422", d("1"), "month", d("300"), d("18")),
            ],
            expected_ledger="6120",
            expected_errors=["tax_split_inconsistent"],
            charge_igst=True,
        ),
        Bill(
            8, "buyer-not-client", "invoice", "buyer_not_client", "dev", "C001",
            V_PROPERTY, OTHER_BUYER, "RP/RENT/26-27/07", date(2026, 10, 1), "dd mon yyyy",
            [Item("Shop rent for October 2026", "997212", d("1"), "month", d("35000"), d("18"))],
            expected_ledger="6100",
            expected_errors=["buyer_not_client"],
        ),
        Bill(
            9, "two-page", "invoice", "happy_two_page", "dev", "C001",
            V_KIRANA, c001, "SLK/26-27/1904", date(2026, 10, 22), "dd-mm-yyyy",
            kirana_items(),
            expected_ledger="5100",
        ),
        Bill(
            10, "scan-quality", "invoice", "happy_degraded_scan", "test", "C002",
            V_PRINTERS, c002, "PP/26-27/0365", date(2026, 9, 29), "dd/mm/yyyy",
            [
                Item("Menu card printing, laminated", "4911", d("200"), "pcs", d("45"), d("18")),
                Item("KOT bill books (100 leaves)", "4820", d("50"), "pcs", d("120"), d("18")),
            ],
            expected_ledger="6150",
            output="scan",
        ),
        Bill(
            11, "fuel-receipt", "receipt", "happy_fuel_receipt", "dev", "C001",
            V_FUEL, None, "NFS-48213", date(2026, 10, 26), "dd/mm/yyyy",
            [Item("Diesel", "2710", d("42.50"), "L", d("92.36"), d("0"))],
            expected_ledger="6130",
            output="photo",
            show_tax=False,
            receipt_time="18:42",
        ),
        Bill(
            12, "restaurant-receipt", "receipt", "happy_restaurant_receipt", "test", "C001",
            V_RESTAURANT, None, "SS/T4/3391", date(2026, 10, 24), "dd-mm-yyyy",
            [
                Item("Veg thali", "996331", d("4"), "plate", d("180"), d("5")),
                Item("Masala chaas", "996331", d("4"), "glass", d("40"), d("5")),
                Item("Gulab jamun (2 pc)", "996331", d("4"), "plate", d("60"), d("5")),
            ],
            expected_ledger="6180",
            output="photo",
            receipt_time="14:05",
        ),
    ]


# ---------------------------------------------------------------- invoice rendering

PAGE_W, PAGE_H = A4
LEFT, RIGHT = 40.0, PAGE_W - 40.0
# (header, left edge, alignment)
COLUMNS = (
    ("#", 40.0, "l"),
    ("Description", 62.0, "l"),
    ("HSN/SAC", 270.0, "l"),
    ("Qty", 365.0, "r"),
    ("Rate", 435.0, "r"),
    ("GST %", 480.0, "r"),
    ("Amount", RIGHT, "r"),
)
ROW_H = 17.0
BOTTOM_MARGIN = 70.0


def _fmt_qty(item: Item) -> str:
    qty = item.quantity.normalize()
    return f"{qty:f} {item.unit}"


def _draw_party(c: Canvas, x: float, y: float, title: str, party: Party, size: float) -> float:
    c.setFont("Helvetica-Bold", size - 1)
    c.drawString(x, y, title)
    y -= size + 3
    c.setFont("Helvetica-Bold", size)
    c.drawString(x, y, party.name)
    c.setFont("Helvetica", size - 1)
    for line in party.address:
        y -= size + 2
        c.drawString(x, y, line)
    y -= size + 2
    c.drawString(x, y, f"State: {STATE_NAMES[party.state_code]} ({party.state_code})")
    if party.gstin:
        y -= size + 2
        c.drawString(x, y, f"GSTIN: {party.gstin}")
    return y


def _draw_header(c: Canvas, bill: Bill) -> float:
    vendor = bill.vendor
    size = 10.0 if bill.layout == "classic" else 9.0
    y = PAGE_H - 50
    if bill.layout == "classic":
        c.setFont("Helvetica-Bold", 17)
        c.drawString(LEFT, y, vendor.name)
        c.setFont("Helvetica-Bold", 14)
        c.drawRightString(RIGHT, y, "TAX INVOICE")
        c.setFont("Helvetica", size)
        for line in vendor.address:
            y -= 13
            c.drawString(LEFT, y, line)
        y -= 13
        c.drawString(LEFT, y, f"GSTIN: {vendor.gstin}   State: {STATE_NAMES[vendor.state_code]} "
                              f"({vendor.state_code})")
    else:
        c.setFont("Helvetica-Bold", 12)
        c.drawCentredString(PAGE_W / 2, y, "TAX INVOICE")
        y -= 20
        c.setFont("Helvetica-Bold", 15)
        c.drawCentredString(PAGE_W / 2, y, vendor.name)
        c.setFont("Helvetica", size)
        y -= 13
        c.drawCentredString(PAGE_W / 2, y, ", ".join(vendor.address))
        y -= 12
        state = f"{STATE_NAMES[vendor.state_code]} ({vendor.state_code})"
        c.drawCentredString(PAGE_W / 2, y, f"GSTIN: {vendor.gstin}  |  State: {state}")
    y -= 10
    c.setLineWidth(1)
    c.line(LEFT, y, RIGHT, y)

    top = y - 16
    assert bill.buyer is not None
    bottom_left = _draw_party(c, LEFT, top, "Bill To:", bill.buyer, size)

    meta = [
        ("Invoice No:", bill.invoice_number),
        ("Invoice Date:", format_date(bill.invoice_date, bill.date_style)),
        ("Place of Supply:", f"{STATE_NAMES[bill.place_of_supply]} ({bill.place_of_supply})"),
        ("Reverse Charge:", "No"),
    ]
    my = top
    for label, value in meta:
        c.setFont("Helvetica-Bold", size)
        c.drawString(340, my, label)
        c.setFont("Helvetica", size)
        c.drawString(430, my, value)
        my -= size + 5
    return min(bottom_left, my) - 18


def _draw_table_header(c: Canvas, bill: Bill, y: float) -> float:
    c.setFont("Helvetica-Bold", 9)
    if bill.layout == "classic":
        c.setFillGray(0.9)
        c.rect(LEFT, y - 5, RIGHT - LEFT, ROW_H, stroke=0, fill=1)
        c.setFillGray(0)
    for title, x, align in COLUMNS:
        if align == "l":
            c.drawString(x + 2, y, title)
        else:
            c.drawRightString(x - 2, y, title)
    c.setLineWidth(0.6)
    c.line(LEFT, y - 6, RIGHT, y - 6)
    return y - ROW_H


def _draw_items(c: Canvas, bill: Bill, y: float) -> float:
    y = _draw_table_header(c, bill, y)
    for index, item in enumerate(bill.items, start=1):
        if y < BOTTOM_MARGIN + 20:
            c.setFont("Helvetica-Oblique", 8)
            c.drawRightString(RIGHT, y, "Continued on next page")
            c.showPage()
            y = PAGE_H - 50
            c.setFont("Helvetica-Bold", 10)
            c.drawString(LEFT, y, f"{bill.vendor.name}  -  Tax Invoice {bill.invoice_number} "
                                  "(continued)")
            y = _draw_table_header(c, bill, y - 24)
        c.setFont("Helvetica", 9)
        values = (
            str(index),
            item.description,
            item.hsn_sac,
            _fmt_qty(item),
            inr(item.rate),
            f"{item.gst_rate.normalize():f}",
            inr(item.amount),
        )
        for (_, x, align), text in zip(COLUMNS, values, strict=True):
            if align == "l":
                c.drawString(x + 2, y, text)
            else:
                c.drawRightString(x - 2, y, text)
        if bill.layout == "classic":
            c.setLineWidth(0.25)
            c.line(LEFT, y - 6, RIGHT, y - 6)
        y -= ROW_H
    c.setLineWidth(0.8)
    c.line(LEFT, y + ROW_H - 6, RIGHT, y + ROW_H - 6)
    return y


def _draw_totals(c: Canvas, bill: Bill, y: float) -> None:
    rows: list[tuple[str, str, bool]] = [("Taxable Value", inr(bill.taxable_value), False)]
    for label, rate, amount in bill.tax_lines():
        rows.append((f"{label} @ {rate.normalize():f}%", inr(amount), False))
    rows.append(("Round Off", inr(bill.round_off), False))
    rows.append(("Grand Total (Rs.)", inr(bill.printed_total), True))

    needed = len(rows) * 15 + 90
    if y - needed < BOTTOM_MARGIN:
        c.showPage()
        y = PAGE_H - 60
    y -= 6
    for label, value, bold in rows:
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 10 if bold else 9)
        c.drawString(360, y, label)
        c.drawRightString(RIGHT - 2, y, value)
        y -= 15
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(LEFT, y - 6, f"Amount in words: {rupees_in_words(bill.printed_total)}")
    y -= 50
    c.setFont("Helvetica", 9)
    c.drawRightString(RIGHT, y, f"For {bill.vendor.name}")
    c.drawRightString(RIGHT, y - 30, "Authorised Signatory")
    c.setFont("Helvetica", 7)
    c.drawString(LEFT, 40, "This is a computer generated invoice. Fictional sample document.")


def render_invoice_pdf(bill: Bill, path: Path) -> None:
    c = Canvas(str(path), pagesize=A4, invariant=1)
    c.setTitle(f"Tax Invoice {bill.invoice_number}")
    y = _draw_header(c, bill)
    y = _draw_items(c, bill, y)
    _draw_totals(c, bill, y)
    c.save()


# ---------------------------------------------------------------- receipt rendering


def _receipt_lines(bill: Bill) -> list[tuple[str, str]]:
    """(text, align) lines for a thermal receipt, 32 characters wide."""
    width = 32

    def lr(left: str, right: str) -> str:
        return left[: width - len(right) - 1].ljust(width - len(right)) + right

    v = bill.vendor
    lines: list[tuple[str, str]] = [(v.name.upper(), "c"), *((a, "c") for a in v.address)]
    if v.gstin:
        lines.append((f"GSTIN: {v.gstin}", "c"))
    lines.append(("-" * width, "l"))
    lines.append((lr(f"Bill: {bill.invoice_number}", bill.receipt_time or ""), "l"))
    lines.append((f"Date: {format_date(bill.invoice_date, bill.date_style)}", "l"))
    lines.append(("-" * width, "l"))
    for item in bill.items:
        lines.append((item.description, "l"))
        lines.append((lr(f"  {_fmt_qty(item)} x {inr(item.rate)}", inr(item.amount)), "l"))
    lines.append(("-" * width, "l"))
    if bill.show_tax:
        lines.append((lr("Sub Total", inr(bill.taxable_value)), "l"))
        for label, rate, amount in bill.tax_lines():
            lines.append((lr(f"{label} @{rate.normalize():f}%", inr(amount)), "l"))
    lines.append((lr("Round Off", inr(bill.round_off)), "l"))
    lines.append((lr("TOTAL Rs.", inr(bill.printed_total)), "l"))
    lines.append(("-" * width, "l"))
    if not bill.show_tax:
        lines.append(("Fuel is outside GST", "c"))
    lines.append(("Thank you! Visit again", "c"))
    return lines


def render_receipt_pdf(bill: Bill, path: Path) -> None:
    lines = _receipt_lines(bill)
    width = 80 * mm
    line_h = 12.0
    height = len(lines) * line_h + 40
    c = Canvas(str(path), pagesize=(width, height), invariant=1)
    y = height - 24
    for text, align in lines:
        bold = text == lines[0][0] or text.startswith("TOTAL")
        c.setFont("Courier-Bold" if bold else "Courier", 9)
        if align == "c":
            c.drawCentredString(width / 2, y, text)
        else:
            c.drawString(10, y, text)
        y -= line_h
    c.save()


# ---------------------------------------------------------------- degrade to scan / photo


def rasterize(pdf_path: Path, dpi: int) -> Image.Image:
    with pymupdf.open(pdf_path) as doc:
        pix = doc[0].get_pixmap(dpi=dpi)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def add_noise(img: Image.Image, amount: float) -> Image.Image:
    noise = Image.effect_noise(img.size, 40).convert(img.mode)
    return Image.blend(img, noise, amount)


def make_scan(pdf_path: Path, out_path: Path, rng: random.Random) -> None:
    img = rasterize(pdf_path, dpi=130).convert("L")
    img = img.rotate(rng.uniform(0.8, 1.4), expand=True, fillcolor=255, resample=Image.BICUBIC)
    img = img.filter(ImageFilter.GaussianBlur(0.7))
    img = add_noise(img, 0.06)
    img = img.point(lambda p: min(255, int(p * 0.95 + 6)))
    img.save(out_path, optimize=True)


def make_photo(pdf_path: Path, out_path: Path, rng: random.Random) -> None:
    receipt = rasterize(pdf_path, dpi=200).convert("L")
    receipt = receipt.point(lambda p: int(p * 0.88 + 14))  # off-white thermal paper
    pad = 140
    background = Image.new("L", (receipt.width + 2 * pad, receipt.height + 2 * pad), 92)
    background.paste(receipt, (pad, pad))
    photo = background.rotate(rng.uniform(2.5, 4.0), fillcolor=92, resample=Image.BICUBIC)
    photo = photo.filter(ImageFilter.GaussianBlur(1.0))
    photo = add_noise(photo, 0.07).convert("RGB")
    photo.save(out_path, quality=82)


# ---------------------------------------------------------------- manifest and checks


def money(value: Decimal) -> str:
    return f"{q2(value):.2f}"


def expected_fields(bill: Bill) -> dict[str, object]:
    fields: dict[str, object] = {
        "vendor_name": bill.vendor.name,
        "vendor_gstin": bill.vendor.gstin,
        "invoice_number": bill.invoice_number,
        "invoice_date": bill.invoice_date.isoformat(),
        "total": money(bill.printed_total),
        "round_off": money(bill.round_off),
        "line_items": [
            {
                "description": item.description,
                "hsn_sac": item.hsn_sac,
                "quantity": f"{item.quantity.normalize():f}",
                "rate": money(item.rate),
                "gst_rate": f"{item.gst_rate.normalize():f}",
                "taxable_amount": money(item.amount),
            }
            for item in bill.items
        ],
    }
    if bill.buyer:
        fields["buyer_name"] = bill.buyer.name
        fields["buyer_gstin"] = bill.buyer.gstin
        fields["place_of_supply"] = bill.place_of_supply
    if bill.show_tax:
        fields["taxable_value"] = money(bill.taxable_value)
        fields["cgst"] = money(bill.tax_total("CGST"))
        fields["sgst"] = money(bill.tax_total("SGST"))
        fields["igst"] = money(bill.tax_total("IGST"))
    return fields


def manifest_entry(bill: Bill, pages: int) -> dict[str, object]:
    return {
        "file": f"generated/{bill.filename}",
        "split": bill.split,
        "client": bill.client_id,
        "type": bill.kind,
        "scenario": bill.scenario,
        "pages": pages,
        "text_layer": bill.output == "pdf",
        "expected_status": "needs_review" if bill.expected_errors else "ready",
        "expected_errors": bill.expected_errors,
        "expected_ledger": bill.expected_ledger,
        "fields": expected_fields(bill),
    }


def check(bill: Bill) -> None:
    """Fail loudly if a document does not contain exactly the problem it is meant to test."""
    errors = set(bill.expected_errors)
    name = bill.filename

    vendor_ok = bill.vendor.gstin is None or gstin_lib.is_valid(bill.vendor.gstin)
    assert vendor_ok == ("invalid_vendor_gstin" not in errors), f"{name}: vendor GSTIN"
    if bill.buyer and bill.buyer.gstin:
        assert gstin_lib.is_valid(bill.buyer.gstin), f"{name}: buyer GSTIN must be valid"
        client = CLIENTS_BY_ID[bill.client_id]
        is_client = bill.buyer.gstin == client.gstin
        assert is_client == ("buyer_not_client" not in errors), f"{name}: buyer vs client"

    intra = bill.vendor.state_code == bill.place_of_supply
    split_ok = not bill.show_tax or bill.is_igst != intra
    assert split_ok == ("tax_split_inconsistent" not in errors), f"{name}: tax split"

    total_ok = bill.printed_total == bill.correct_total
    assert total_ok == ("total_mismatch" not in errors), f"{name}: total"

    assert len(bill.invoice_number) <= 16, f"{name}: invoice number longer than 16"
    assert bill.invoice_date <= TODAY, f"{name}: date in the future"
    if bill.date_style != "dd mon yyyy":
        assert bill.invoice_date.day > 12, f"{name}: numeric date must not be ambiguous"
    assert abs(bill.round_off) < 1, f"{name}: round off"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.iterdir():
        if old.suffix in {".pdf", ".png", ".jpg"}:
            old.unlink()

    rng = random.Random(2026)
    entries = []
    for bill in build_corpus():
        check(bill)
        target = OUT_DIR / bill.filename
        pdf_path = target if bill.output == "pdf" else OUT_DIR / f"_{bill.number:02d}.pdf"
        if bill.kind == "invoice":
            render_invoice_pdf(bill, pdf_path)
        else:
            render_receipt_pdf(bill, pdf_path)
        with pymupdf.open(pdf_path) as doc:
            pages = doc.page_count
        if bill.output == "scan":
            make_scan(pdf_path, target, rng)
        elif bill.output == "photo":
            make_photo(pdf_path, target, rng)
        if pdf_path != target:
            pdf_path.unlink()
        entries.append(manifest_entry(bill, pages))
        status = "needs_review" if bill.expected_errors else "ready"
        print(f"  {bill.filename:<32} {pages}p  {status:<13} {', '.join(bill.expected_errors)}")

    manifest = {
        "description": "Fictional GST invoices and receipts. Generated by "
        "backend/scripts/generate_samples.py; do not edit by hand.",
        "documents": entries,
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")
    print(f"Wrote {len(entries)} documents to {OUT_DIR} and {MANIFEST_PATH.name}")


if __name__ == "__main__":
    main()
