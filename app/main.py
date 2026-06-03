# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles  
from fastapi.responses import FileResponse   
from contextlib import asynccontextmanager
from pathlib import Path                     


from app.api.routes import router
from app.api.admin import admin_router
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
app.include_router(admin_router)
static_dir = Path(__file__).parent.parent / "frontend"
if static_dir.exists():
    app.mount("/frontend", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse(str(static_dir / "index.html"))



if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=int(__import__("os").environ.get("PORT", "8000")), reload=False)
