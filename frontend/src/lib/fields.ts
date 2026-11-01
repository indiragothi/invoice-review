// Pure helpers for the flat `review_data.fields` map. Paths look like `vendor_gstin`,
// `line_items[2].taxable_amount`, `tax_lines[0].amount`.

import type { ReviewData } from './types.ts'

const TOP_LABELS: Record<string, string> = {
  vendor_name: 'Vendor name',
  vendor_gstin: 'Vendor GSTIN',
  buyer_name: 'Buyer name',
  buyer_gstin: 'Buyer GSTIN',
  invoice_number: 'Invoice number',
  invoice_date: 'Invoice date',
  place_of_supply: 'Place of supply',
  reverse_charge: 'Reverse charge',
  taxable_value: 'Taxable value',
  round_off: 'Round off',
  total: 'Total',
  amount_in_words: 'Amount in words',
  merchant_name: 'Merchant',
  merchant_gstin: 'Merchant GSTIN',
  receipt_number: 'Receipt number',
  receipt_date: 'Date',
  payment_method: 'Payment method',
}

const ITEM_LABELS: Record<string, string> = {
  description: 'Description',
  hsn_sac: 'HSN / SAC',
  quantity: 'Quantity',
  rate: 'Rate',
  gst_rate: 'GST rate',
  taxable_amount: 'Taxable amount',
  amount: 'Amount',
}

const TAX_LABELS: Record<string, string> = { rate: 'Rate', amount: 'Amount' }

function words(name: string): string {
  const text = name.replace(/_/g, ' ')
  return text.charAt(0).toUpperCase() + text.slice(1)
}

const ITEM_PATH = /^line_items\[(?<index>\d+)\]\.(?<name>\w+)$/
const TAX_PATH = /^tax_lines\[(?<index>\d+)\]\.(?<name>\w+)$/

/** `{ index, name }` of an indexed path, or null for a header path. */
function parseIndexed(pattern: RegExp, path: string): { index: number; name: string } | null {
  const groups = pattern.exec(path)?.groups
  if (!groups?.index || !groups.name) return null
  return { index: Number(groups.index), name: groups.name }
}

/** A short label for a field path ("Vendor GSTIN", "Taxable amount"). */
export function fieldLabel(path: string): string {
  const item = parseIndexed(ITEM_PATH, path)
  if (item) return ITEM_LABELS[item.name] ?? words(item.name)
  const tax = parseIndexed(TAX_PATH, path)
  if (tax) return TAX_LABELS[tax.name] ?? words(tax.name)
  return TOP_LABELS[path] ?? words(path)
}

export interface FieldGroups {
  header: string[]
  /** One list of paths per line item, in order. */
  lineItems: { index: number; paths: string[] }[]
  taxLines: { index: number; paths: string[] }[]
}

function collect(
  into: { index: number; paths: string[] }[],
  index: number,
  path: string,
): void {
  const found = into.find((group) => group.index === index)
  if (found) found.paths.push(path)
  else into.push({ index, paths: [path] })
}

/** Splits the paths into header fields, line items and tax lines, keeping the server's order. */
export function groupFields(data: ReviewData): FieldGroups {
  const groups: FieldGroups = { header: [], lineItems: [], taxLines: [] }
  for (const path of Object.keys(data.fields)) {
    const item = parseIndexed(ITEM_PATH, path)
    const tax = parseIndexed(TAX_PATH, path)
    if (item) collect(groups.lineItems, item.index, path)
    else if (tax) collect(groups.taxLines, tax.index, path)
    else groups.header.push(path)
  }
  return groups
}
