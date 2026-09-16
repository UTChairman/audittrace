const FIELD_LABELS: Record<string, string> = {
  vendor_name: "Vendor name",
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  po_number: "PO number",
  order_date: "Order date",
  subtotal: "Subtotal",
  tax: "Tax",
  total: "Total",
  currency: "Currency",
  currency_suggested: "Suggested currency",
};

const LINE_ATTR: Record<string, string> = {
  description: "Description",
  detail: "Detail",
  quantity: "Quantity",
  unit_price: "Unit price",
  amount: "Amount",
};

const CHECK_TYPE_LABELS: Record<string, string> = {
  invoice_dated_before_po: "Invoice dated before PO",
  duplicate_po_number: "Duplicate PO number",
  duplicate_invoice_number: "Duplicate invoice number",
  duplicate_document: "Duplicate document",
  line_item_price_mismatch: "Line item price mismatch",
  line_item_quantity_mismatch: "Line item quantity mismatch",
  line_item_not_on_po: "Line item not on PO",
  vendor_mismatch: "Vendor mismatch",
  total_mismatch: "Total mismatch",
};

const REVIEW_STATUS_LABELS: Record<string, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  edited: "Edited",
};

const ACTION_LABELS: Record<string, string> = {
  approve: "Approve",
  reject: "Reject",
  edit: "Edit",
  reset: "Reset to pending",
  recalculate_findings: "Findings recalculated",
};

const LINE_ITEM = /^line_items\[(\d+)\]\.(.+)$/;

export function fieldLabel(fieldName: string | null | undefined): string {
  if (!fieldName) return "—";
  const line = fieldName.match(LINE_ITEM);
  if (line) {
    const index = Number(line[1]) + 1;
    const attr = LINE_ATTR[line[2]] ?? titleCase(line[2]);
    return `Line ${index} · ${attr}`;
  }
  return FIELD_LABELS[fieldName] ?? titleCase(fieldName);
}

export function checkTypeLabel(checkType: string): string {
  return CHECK_TYPE_LABELS[checkType] ?? titleCase(checkType);
}

export function reviewStatusLabel(status: string): string {
  return REVIEW_STATUS_LABELS[status] ?? titleCase(status);
}

export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? titleCase(action);
}

export function isMoneyField(fieldName: string): boolean {
  return (
    fieldName === "total" ||
    fieldName === "subtotal" ||
    fieldName === "tax" ||
    fieldName.endsWith(".unit_price") ||
    fieldName.endsWith(".amount")
  );
}

export function formatAmount(value: number, currency: string | null | undefined): string {
  const amount = value.toFixed(2);
  const token = currency?.trim();
  if (!token) return amount;
  if (token.length === 1) return `${token}${amount}`;
  return `${token} ${amount}`;
}

export function formatFieldValue(
  fieldName: string,
  value: unknown,
  currency: string | null | undefined
): string {
  if (value === null || value === undefined || value === "") return "—";
  if (isMoneyField(fieldName)) {
    const number = typeof value === "number" ? value : Number(value);
    if (Number.isFinite(number)) return formatAmount(number, currency);
  }
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}

export function editSeedValue(fieldName: string, value: unknown): string {
  if (value === null || value === undefined) return "";
  if (isMoneyField(fieldName) && typeof value === "number") return value.toFixed(2);
  if (typeof value === "string" || typeof value === "number") return String(value);
  return JSON.stringify(value);
}

function titleCase(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}
