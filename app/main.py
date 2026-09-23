from fastapi import FastAPI

from app.api.routes import router


app = FastAPI(
    title="Smart Contractor Recommendation API",
    version="1.0.0",
    description="API for selecting event contractors.",
)

app.include_router(router)


@app.get("/")
def root() -> dict[str, str]:
    return {
        "message": "Smart Contractor Recommendation API",
        "status": "ok",
    }