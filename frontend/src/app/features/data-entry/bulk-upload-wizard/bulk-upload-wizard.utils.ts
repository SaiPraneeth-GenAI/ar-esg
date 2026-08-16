export interface TargetField {
  key: string;
  label: string;
  required: boolean;
  synonyms: string[];
}

export const TARGET_FIELDS: TargetField[] = [
  {
    key: 'category',
    label: 'Category',
    required: false,
    synonyms: ['category', 'section', 'group', 'input group']
  },
  {
    key: 'data_point_name',
    label: 'Data point',
    required: true,
    synonyms: ['data point name', 'data point', 'field', 'metric', 'parameter', 'name', 'item']
  },
  {
    key: 'period',
    label: 'Period / Month',
    required: false,
    synonyms: ['period', 'month', 'date', 'reporting period', 'period month']
  },
  { key: 'value', label: 'Value', required: true, synonyms: ['value', 'reading', 'amount', 'qty', 'quantity', 'total'] },
  { key: 'unit', label: 'Unit', required: false, synonyms: ['unit', 'uom', 'units'] },
  { key: 'note', label: 'Note', required: false, synonyms: ['note', 'notes', 'comment', 'remarks', 'remark'] }
];

export async function parseSpreadsheet(file: File): Promise<{ headers: string[]; rows: unknown[][] }> {
  // Dynamically imported so the ~350kB xlsx parser only loads when someone
  // actually drops a file, not every time the Data Entry screen opens.
  const XLSX = await import('xlsx');
  const buffer = await file.arrayBuffer();
  const workbook = XLSX.read(buffer, { type: 'array', cellDates: true });
  const sheet = workbook.Sheets[workbook.SheetNames[0]];
  const data = XLSX.utils.sheet_to_json<unknown[]>(sheet, { header: 1, raw: true, defval: '' });
  const headers = (data[0] || []).map((h) => String(h ?? '').trim());
  const rows = data.slice(1).filter((r) => r.some((c) => c !== '' && c !== null && c !== undefined));
  return { headers, rows };
}

function normalize(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
}

export function guessMapping(headers: string[]): (string | null)[] {
  const used = new Set<string>();
  return headers.map((header) => {
    const norm = normalize(header);
    if (!norm) {
      return null;
    }

    for (const field of TARGET_FIELDS) {
      if (used.has(field.key)) {
        continue;
      }
      if (field.synonyms.some((syn) => normalize(syn) === norm)) {
        used.add(field.key);
        return field.key;
      }
    }

    let best: { key: string; score: number } | null = null;
    for (const field of TARGET_FIELDS) {
      if (used.has(field.key)) {
        continue;
      }
      for (const syn of field.synonyms) {
        const synNorm = normalize(syn);
        if (norm.includes(synNorm) || synNorm.includes(norm)) {
          const score = Math.min(norm.length, synNorm.length) / Math.max(norm.length, synNorm.length);
          if (!best || score > best.score) {
            best = { key: field.key, score };
          }
        }
      }
    }
    if (best && best.score > 0.4) {
      used.add(best.key);
      return best.key;
    }
    return null;
  });
}

const MONTH_NAMES = [
  'january',
  'february',
  'march',
  'april',
  'may',
  'june',
  'july',
  'august',
  'september',
  'october',
  'november',
  'december'
];

export function parsePeriodToIso(raw: unknown): string | null {
  if (raw instanceof Date && !isNaN(raw.getTime())) {
    return `${raw.getFullYear()}-${String(raw.getMonth() + 1).padStart(2, '0')}-01`;
  }

  if (typeof raw === 'number') {
    const ms = Date.UTC(1899, 11, 30) + raw * 86400000;
    const d = new Date(ms);
    if (!isNaN(d.getTime())) {
      return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}-01`;
    }
  }

  const str = String(raw ?? '').trim();
  if (!str) {
    return null;
  }

  let m = str.match(/^(\d{4})-(\d{1,2})(-\d{1,2})?$/);
  if (m) {
    return `${m[1]}-${m[2].padStart(2, '0')}-01`;
  }

  m = str.match(/^(\d{1,2})[/-](\d{4})$/);
  if (m) {
    return `${m[2]}-${m[1].padStart(2, '0')}-01`;
  }

  m = str.match(/^([a-zA-Z]+)[\s-]?'?(\d{2,4})$/);
  if (m) {
    const monthIndex = MONTH_NAMES.findIndex((mn) => mn.startsWith(m![1].toLowerCase()));
    if (monthIndex >= 0) {
      let year = parseInt(m[2], 10);
      if (year < 100) {
        year += 2000;
      }
      return `${year}-${String(monthIndex + 1).padStart(2, '0')}-01`;
    }
  }

  const d = new Date(str);
  if (!isNaN(d.getTime())) {
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`;
  }

  return null;
}

export function formatPeriodLabel(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  if (isNaN(d.getTime())) {
    return iso;
  }
  return d.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
}
