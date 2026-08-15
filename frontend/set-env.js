const fs = require('fs');
const path = require('path');

const supabaseUrl = process.env['SUPABASE_URL'] || '';
const supabaseAnonKey = process.env['SUPABASE_ANON_KEY'] || '';
const apiBaseUrl = process.env['API_BASE_URL'] || '';

const content = `export const environment = {
  production: true,
  supabaseUrl: '${supabaseUrl}',
  supabaseAnonKey: '${supabaseAnonKey}',
  apiBaseUrl: '${apiBaseUrl}',
};
`;

const outPath = path.join(__dirname, 'src', 'environments', 'environment.prod.ts');
fs.writeFileSync(outPath, content);
console.log(`Wrote ${outPath}`);
