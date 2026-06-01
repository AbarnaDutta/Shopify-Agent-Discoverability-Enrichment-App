# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api.routes import router
from app.services.jobs import job_queue
from app.core.database import init_db    


@asynccontextmanager
async def lifespan(app: FastAPI):
    # start background worker on application startup
    init_db()                               
    job_queue.start()
    try:
        yield
    finally:
        # no explicit shutdown action required for job_queue
        pass


app = FastAPI(title="Shopify Agent Enrichment App", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=int(__import__("os").environ.get("PORT", "8000")), reload=False)
