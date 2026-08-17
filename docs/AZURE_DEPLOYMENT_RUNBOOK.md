# Azure Deployment Runbook

Target architecture: **backend on Azure Container Apps**, **frontend on Azure Static Web Apps**. Supabase (DB + auth) is unchanged -- it's a separate managed service, not tied to Render, so nothing about it moves.

This is a parallel deployment, not a migration-in-place: Render keeps running untouched throughout. Nothing here is destructive until the explicit cutover step at the end, and even that is just a DNS/URL change you make when ready.

## What's already prepared in the repo

- `backend/Dockerfile` -- tweaked to read `$PORT` from the environment (defaults to 8000, so Render is unaffected).
- `.github/workflows/azure-backend.yml` -- builds the backend image, pushes to Azure Container Registry, deploys to Container Apps. Manual trigger (`workflow_dispatch`) until you're ready to make it automatic.
- `.github/workflows/azure-frontend.yml` -- builds the Angular app (using the same `set-env.js` step Render's build already runs) and deploys to Static Web Apps. Also manual trigger.
- `frontend/public/staticwebapp.config.json` -- SPA fallback routing (so a deep link like `/admin/targets` doesn't 404 on refresh), the Static Web Apps equivalent of whatever rewrite rule Render's dashboard has configured today.

## Step 1 -- Prerequisites

- An Azure subscription (with permission to create resource groups).
- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli) installed and logged in: `az login`.
- This repo's secrets from `CLAUDE.md` / your password manager on hand -- you'll re-enter the same values Render already has, into Azure's equivalents.

## Step 2 -- Create the resource group and registry

```bash
RG=envigo-rg
LOCATION=centralindia   # pick the Azure region closest to your users

az group create --name $RG --location $LOCATION

az acr create --resource-group $RG --name envigoacr --sku Basic --admin-enabled false
```

## Step 3 -- Container Apps environment + the backend app

```bash
az extension add --name containerapp --upgrade

az containerapp env create \
  --name envigo-env \
  --resource-group $RG \
  --location $LOCATION

# First deploy from a placeholder image -- the GitHub Actions workflow
# will push the real one and update it on every run afterward.
az containerapp create \
  --name envigo-backend \
  --resource-group $RG \
  --environment envigo-env \
  --image mcr.microsoft.com/k8se/quickstart:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 3
```

Then set every environment variable the backend needs (same names as `backend/app/core/config.py`, same values already on Render):

```bash
az containerapp update --name envigo-backend --resource-group $RG --set-env-vars \
  ENVIRONMENT=production \
  DATABASE_URL="<same as Render>" \
  SUPABASE_URL="<same as Render>" \
  SUPABASE_ANON_KEY="<same as Render>" \
  SUPABASE_SERVICE_ROLE_KEY="<same as Render>" \
  SUPABASE_JWT_SECRET="<same as Render>" \
  SECRET_KEY="<same as Render>" \
  ENCRYPTION_KEY="<same as Render>" \
  OPENAI_API_KEY="<same as Render>" \
  SMTP_HOST="<same as Render>" \
  SMTP_PORT="<same as Render>" \
  SMTP_USERNAME="<same as Render>" \
  SMTP_APP_PASSWORD="<same as Render>" \
  EMAIL_PROVIDER_API_KEY="<same as Render>" \
  EMAIL_FROM="<same as Render>" \
  FRONTEND_URL="https://<your-static-web-app-hostname>" \
  CORS_ALLOWED_ORIGINS="https://<your-static-web-app-hostname>"
```

Grab the backend's public URL for later:

```bash
az containerapp show --name envigo-backend --resource-group $RG \
  --query properties.configuration.ingress.fqdn -o tsv
```

## Step 4 -- Static Web App for the frontend

```bash
az staticwebapp create \
  --name envigo-frontend \
  --resource-group $RG \
  --location $LOCATION \
  --sku Free
```

Grab its deployment token (needed as a GitHub secret below):

```bash
az staticwebapp secrets list --name envigo-frontend --resource-group $RG \
  --query properties.apiKey -o tsv
```

## Step 5 -- Wire up GitHub Actions

Give GitHub a way to authenticate to Azure without a long-lived secret (federated OIDC, recommended):

```bash
az ad app create --display-name envigo-github-deploy
# note the appId -- that's AZURE_CLIENT_ID below
az ad sp create --id <appId>

az ad app federated-credential create --id <appId> --parameters '{
  "name": "github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:SaiPraneeth-GenAI/ar-esg:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'

# grant it Contributor on the resource group
az role assignment create --assignee <appId> --role Contributor \
  --scope /subscriptions/<subscription-id>/resourceGroups/$RG
```

In the GitHub repo (**Settings > Secrets and variables > Actions**):

**Repository secrets:**
| Name | Value |
|---|---|
| `AZURE_CLIENT_ID` | the `appId` from above |
| `AZURE_TENANT_ID` | `az account show --query tenantId -o tsv` |
| `AZURE_SUBSCRIPTION_ID` | `az account show --query id -o tsv` |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | the deployment token from Step 4 |
| `FRONTEND_SUPABASE_URL` | same value as Render's `SUPABASE_URL` |
| `FRONTEND_SUPABASE_ANON_KEY` | same value as Render's `SUPABASE_ANON_KEY` |

**Repository variables:**
| Name | Value |
|---|---|
| `AZURE_RESOURCE_GROUP` | `envigo-rg` |
| `AZURE_CONTAINER_APP_NAME` | `envigo-backend` |
| `AZURE_ACR_LOGIN_SERVER` | `envigoacr.azurecr.io` |
| `AZURE_BACKEND_URL` | `https://<the fqdn from Step 3>` |

Also grant the GitHub Actions identity push access to the registry:

```bash
az role assignment create --assignee <appId> --role AcrPush \
  --scope /subscriptions/<subscription-id>/resourceGroups/$RG/providers/Microsoft.ContainerRegistry/registries/envigoacr
```

## Step 6 -- First deploy

In GitHub, run each workflow manually once (**Actions tab > select workflow > Run workflow**):

1. `Deploy backend to Azure Container Apps`
2. `Deploy frontend to Azure Static Web Apps`

## Step 7 -- Verify before cutover

- Hit `https://<container-app-fqdn>/health` -- should return 200, same as Render's `/health` does today.
- Open the Static Web Apps URL, log in, click through Dashboard / Data Entry / Charts / Targets -- confirm it talks to the new backend (check the Network tab for calls to the Container App URL, not Render).
- Test the PDF/PPTX export specifically -- it's the heaviest request path (matplotlib + reportlab/pptx + an OpenAI call) and the one most likely to reveal a Container Apps cold-start or memory-limit issue Render's config didn't have.

## Step 8 -- Cutover (only when you're ready)

- If using a custom domain, repoint DNS to the Static Web App and Container App instead of the `*.onrender.com` hostnames.
- Update `CORS_ALLOWED_ORIGINS` on the Container App to the final custom domain (not just the `*.azurestaticapps.net` one).
- Once traffic has been on Azure for a while with no issues, suspend (don't delete yet) the two Render services -- keep them as a rollback path for a week or two before decommissioning for good.

## Rollback

At any point before Step 8, rollback is free: nothing about Render changed, so simply stop using the Azure URLs and keep pointing users at the existing `*.onrender.com` addresses.
