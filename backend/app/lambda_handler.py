from mangum import Mangum

from app.main import app


# API Gateway HTTP API payload v2 adapter. Lifespan is disabled because the
# application has no startup/shutdown hooks and this reduces cold-start work.
handler = Mangum(app, lifespan="off")
