# ar-esg (Envigo)

ESG data collection, approval, and compliance-reporting platform.

## Structure

- `backend/` — FastAPI + SQLAlchemy, Dockerized. Deployed as a Render web service.
- `frontend/` — Angular app. Deployed as a Netlify site.
- `docs/` — data model, data dictionary, and other reference docs.
- `backend/migrations/0001_init_schema.sql` — full Postgres schema matching `docs/data_model_and_dictionary.md`.

## Local development

**Backend**
```
cd backend
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env   # fill in local values
uvicorn app.main:app --reload
```

**Frontend**
```
cd frontend
npm install
npm start
```

## Deployment

- Backend: Render web service, root directory `backend`, Docker runtime. Auto-deploys from `main`.
- Frontend: Netlify site, base directory `frontend`, build command `npm run build:netlify`, publish directory `dist/frontend/browser`. Auto-deploys from `main`.

Secrets are never committed — they're set as environment variables directly on Render/Netlify.
