import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.data.loader import load_contractors


@asynccontextmanager
async def lifespan(app: FastAPI):
    path = os.environ.get("CONTRACTORS_CSV_PATH")

    if not path:
        raise RuntimeError(
            "Укажите путь к CSV в CONTRACTORS_CSV_PATH"
        )

    app.state.contractors = load_contractors(path)
    yield


app = FastAPI(
    title="Smart Contractor Recommendation API",
    version="1.0.0",
    description="API for selecting event contractors.",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Smart Contractor Recommendation API",
        "status": "ok",
    }