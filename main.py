from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from db.connection import init_db
from api.routes import router

DB_CONNECTED = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global DB_CONNECTED
    try:
        await init_db()
        DB_CONNECTED = True
    except Exception:
        DB_CONNECTED = False
    yield


app = FastAPI(title="Competitor Intelligence Agent", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["null", "http://localhost", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "db": "connected" if DB_CONNECTED else "error",
    }
