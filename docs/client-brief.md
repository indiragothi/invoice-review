# Client Brief

## The firm

**Mehta & Associates, Chartered Accountants** is a (fictional) small CA firm in India. It handles GST filing and bookkeeping for about 60 small clients: traders, restaurants, clinics, workshops.

Every month each client sends a bundle of purchase and expense documents: GST tax invoices, supplier bills, shop receipts, fuel slips. They arrive as digital PDFs, scans, WhatsApp photos and screenshots, mostly in English, sometimes with Hindi text.

## The user

**Priya** is an accounts executive at the firm. Before the GST return deadlines she types 150-300 documents a day into Tally / Excel by hand. For each one she has to:

1. Work out whether it is a tax invoice or a plain receipt.
2. Read vendor, GSTIN, invoice number, date, line items, tax and total.
3. Check the arithmetic, the GSTIN, and the CGST / SGST / IGST split, because a wrong GSTIN or tax split puts the client's input tax credit (ITC) at risk.
4. Check the bill is actually addressed to the client (buyer GSTIN = client GSTIN).
5. Notice duplicates (the same bill sent twice, once as a photo and once as a PDF).

It is repetitive and error-prone, and one typo can cost a client money.

## The problem in one line

> Manual entry of GST bills is slow and error-prone, and the errors that matter (wrong GSTIN, bad tax split, mismatched totals, duplicates) are exactly the ones a tired person misses.

## User story

> As an accounts executive, I want every uploaded bill to arrive as a **prepared review**: extracted fields, validation results, and the exact place on the page each value came from. Then I can approve the clean ones quickly and spend my time only on the ones that need a human.

## Core requirement

The app **reads, checks and suggests. It does not decide.** Priya makes the final call.

> Models extract evidence. Code decides policy. The human owns the decision.

## What is in v1

- Pick a client, then upload one PDF or image per document (max 5 MB, max 5 pages; JPG, PNG, PDF).
- Classify the document as `invoice` or `receipt`.
- Extract into a fixed structure: vendor, vendor GSTIN, buyer, buyer GSTIN, invoice number, date, place of supply, line items (description, HSN/SAC, qty, rate, taxable amount, GST rate), taxable value, CGST / SGST / IGST, cess, round-off, total.
- Validate with deterministic Python (see [policy-rules.md](policy-rules.md)): GSTIN format and checksum, buyer = client, arithmetic, tax split, dates, duplicates.
- Give every field a confidence and a **source** (which words on the page, which reading, or human).
- Route anything with errors or low confidence to a **review screen** instead of saving it.
- Review screen: page on one side with the source box highlighted, editable fields on the other. Clicking a field highlights its box; clicking a box selects its field.
- Priya can correct fields, approve, or reject. Corrections re-run validation. Clean (`ready`) documents can be approved in bulk.
- Export approved records to CSV / Excel (one row per document and one sheet of line items).
- Review history (audit log), with explicit delete so demos can be reset.
- A ground-truth sample set (36+ documents) and an evaluation script reporting field-level accuracy.

## Stretch (after v1 works)

- Hindi + English bills.
- Handwritten receipts.
- Tally-friendly import format.
- **GSTR-2B reconciliation:** match approved purchase invoices against the client's GSTR-2B JSON and list missing / mismatched ones. This is the single most valuable next feature for a CA firm.
- Run both providers on every document and compare.

## Out of scope

Login and multiple users, multi-firm tenancy, email or WhatsApp ingestion, queues and workers, GST portal / e-invoice (IRN) verification, live GSTIN status lookup, ITC eligibility decisions (e.g. blocked credits), payments, filing returns, and any tax advice. This is a portfolio-grade pipeline, not a production accounting product.

## Success criteria

- Field-level accuracy reported on **30+ documents** (target 36+) against ground truth, on a held-out test split.
- **No record with a blocking validation error can be approved or exported** without a human correcting it. Enforced in the service layer and checked by the evaluation script.
- Every displayed value links back to a region of the page.
- Roadmap extras: security pass, live deployment, demo video.

## Data and privacy

Free-tier LLM APIs may use submitted data for model improvement. So only fictional, synthetic or fully redacted documents go through this project. Real client bills must never be committed or sent to a free-tier API.
