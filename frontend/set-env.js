const fs = require('fs');
const path = require('path');

const cognitoUserPoolId = process.env['COGNITO_USER_POOL_ID'] || '';
const cognitoAppClientId = process.env['COGNITO_APP_CLIENT_ID'] || '';
const apiBaseUrl = process.env['API_BASE_URL'] || '';

const content = `export const environment = {
  production: true,
  cognitoUserPoolId: '${cognitoUserPoolId}',
  cognitoAppClientId: '${cognitoAppClientId}',
  apiBaseUrl: '${apiBaseUrl}',
};
`;

const outPath = path.join(__dirname, 'src', 'environments', 'environment.prod.ts');
fs.writeFileSync(outPath, content);
console.log(`Wrote ${outPath}`);
