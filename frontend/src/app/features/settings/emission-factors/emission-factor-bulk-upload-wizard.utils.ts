export interface ParsedSheet {
  name: string;
  headers: string[];
  rows: string[][];
}

function cellToString(value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }
  if (value instanceof Date) {
    return value.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  }
  return String(value).trim();
}

/**
 * Reads every sheet in the workbook, as raw grids of strings. Deliberately
 * keeps blank rows (the backend uses them to split a sheet with more than
 * one table -- e.g. a small refrigerant-GWP table sitting further down
 * the same Scope-1 tab) -- unlike the entries bulk-upload parser, which
 * drops them.
 */
export async function parseWorkbookAllSheets(file: File): Promise<ParsedSheet[]> {
  // Dynamically imported so the ~350kB xlsx parser only loads when an Admin
  // actually drops a file on this screen.
  const XLSX = await import('xlsx');
  const buffer = await file.arrayBuffer();
  const workbook = XLSX.read(buffer, { type: 'array', cellDates: true });

  const sheets: ParsedSheet[] = [];
  for (const name of workbook.SheetNames) {
    const sheet = workbook.Sheets[name];
    const data = XLSX.utils.sheet_to_json<unknown[]>(sheet, { header: 1, raw: true, defval: '' });
    if (data.length === 0) {
      continue;
    }
    const grid = data.map((row) => row.map(cellToString));
    const headers = grid[0] ?? [];
    const rows = grid.slice(1);
    if (!headers.some((h) => h)) {
      continue;
    }
    sheets.push({ name, headers, rows });
  }
  return sheets;
}

export const STATUS_LABEL: Record<string, string> = {
  ready: 'Ready',
  needs_confirmation: 'Needs confirmation',
  missing_source: 'Missing source',
  error: 'Error',
  skip: 'Skip',
  unchecked: 'Unchecked',
  created: 'Created'
};

export const COLUMN_ROLE_LABEL: Record<string, string> = {
  name: 'Substance / fuel / activity name',
  method: 'Method (location/market-based)',
  scope3_category: 'Scope 3 category',
  description: 'Description',
  unit: 'Unit / UOM',
  source: 'Source (standard/body)',
  source_reference: 'Source reference',
  value: 'Factor value',
  year_value: 'Factor value (year-specific)',
  skip: 'Skip -- not a factor'
};

export const COLUMN_ROLE_OPTIONS = Object.keys(COLUMN_ROLE_LABEL);
