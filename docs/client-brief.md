# Client Brief

## The firm

**Mehta & Associates, Chartered Accountants** is a (fictional) small CA firm in India. It handles GST filing and bookkeeping for small clients: traders, restaurants, clinics, workshops.

Every month each client sends a bundle of purchase and expense documents: GST tax invoices, supplier bills, shop receipts, fuel slips. They arrive as digital PDFs, scans, WhatsApp photos and screenshots, mostly in English, sometimes with Hindi text.

All product copy, source code and documentation are in English. Only the sample bills vary.

## The user

**Priya** is an accounts executive at the firm. Before the GST return deadlines she types 150-300 documents a day into Tally / Excel by hand. For each one she has to:

1. Work out whether it is a tax invoice or a plain receipt.
2. Read vendor, GSTIN, invoice number, date, line items, tax and total.
3. Check the arithmetic, the GSTIN, and the CGST / SGST / IGST split, because a wrong GSTIN or tax split puts the client's input tax credit (ITC) at risk.
4. Check the bill is actually addressed to the client (buyer GSTIN = client GSTIN).
5. Notice duplicates (the same bill sent twice, once as a photo and once as a PDF).
6. Post it to the right ledger (Rent, Fuel, Purchase, Repairs ...).
7. When the supplier made a mistake, write to them asking for a corrected invoice.

It is repetitive and error-prone, and one typo can cost a client money.

## The problem in one line

> Manual entry of GST bills is slow and error-prone, and the errors that matter (wrong GSTIN, bad tax split, mismatched totals, duplicates) are exactly the ones a tired person misses.

## User story

> As an accounts executive at a CA firm, I want to upload a client's invoice or receipt and receive a prepared review: the best combined extraction, GST and policy results, the place on the page each value came from, and a suggested ledger. Then I can approve valid documents quickly and turn supplier errors into a clear correction request.

## Core requirement

The app **reads, checks and suggests. It does not decide.** Priya makes the final call.

> Models extract evidence. Code decides policy. The human owns the decision.

## What's included in the build

This mirrors the scope of the reference build ([e2e-invoice-review](https://github.com/daveebbelaar/e2e-invoice-review)), with free providers instead of Azure and Indian GST instead of EU VAT.

| Reference build (Azure, EU) | This build (free, India) |
|---|---|
| One PDF / image per upload, 4 MB | Same, 5 MB, max 5 pages |
| Invoice / receipt recognition (Azure OpenAI) | Same, Gemini via pydantic-ai |
| Document Intelligence prebuilt extraction (primary) | PDF text layer / RapidOCR words + LLM extraction with evidence word IDs (primary reading) |
| Independent Azure OpenAI extraction, merge fills gaps | Independent vision reading, merge fills gaps; agree / differ shown |
| Field provenance | Same, **plus a highlighted box on the page for every value** |
| EU VAT format / checksum (offline) | GSTIN format / checksum (offline), buyer = client, CGST/SGST/IGST split |
| Separate invoice and receipt policies, duplicate detection | Same, plus line items must add up |
| Fixed GL catalog + LLM suggestion, reviewer can override | Fixed **ledger catalog** (Tally-style heads) + LLM suggestion, Priya can override |
| Corrections, approve, reject | Same, plus bulk-approve of clean documents |
| Correction-email draft, never sent | Same: "please issue a corrected invoice / credit note" |
| SQLite, local files, welcome → upload → process → review flow | Same |
| Review history with explicit delete | Same |
| 13-document corpus | 36+ documents with a dev / test split (roadmap asks for 30+) |
| Shared-password gate for the deployed demo | Same |
| — | Export approved records to CSV / Excel |

### Clients

The firm works *for* clients, so every upload is tagged with one. In v1 the clients are a small fixed list in configuration (name, GSTIN, state), like Northstar is fixed in the reference build. There is no client management screen.

## Stretch (after v1 works)

- Hindi + English bills.
- Handwritten receipts.
- Tally-friendly import format.
- **GSTR-2B reconciliation:** match approved purchase invoices against the client's GSTR-2B JSON and list missing / mismatched ones. The most valuable next feature for a CA firm.
- Run both providers on every document and compare.

## Out of scope

User accounts and roles (only one shared demo password), client management, multi-firm tenancy, email or WhatsApp ingestion, sending email, queues and workers, GST portal / e-invoice (IRN) verification, live GSTIN status lookup, ITC eligibility decisions (e.g. blocked credits), accounting-software integration beyond file export, payments, filing returns, and any tax advice. This is a portfolio-grade pipeline, not a production accounting product.

## Success criteria

- Field-level accuracy reported on **30+ documents** (target 36+) against ground truth, on a held-out test split.
- **No record with a blocking validation error can be approved or exported** without a human correcting it. Enforced in the service layer and checked by the evaluation script.
- Every displayed value links back to a region of the page.
- Roadmap extras: security pass, live deployment, demo video.

## Data and privacy

Free-tier LLM APIs may use submitted data for model improvement. So only fictional, synthetic or fully redacted documents go through this project. Real client bills must never be committed or sent to a free-tier API.
