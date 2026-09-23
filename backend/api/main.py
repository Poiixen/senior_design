from fastapi import FastAPI

app = FastAPI(title="Team Science API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
