from fastapi import FastAPI

app = FastAPI(title="Project Inception API")


@app.get("/health")
def health():
    return {"status": "ok"}
