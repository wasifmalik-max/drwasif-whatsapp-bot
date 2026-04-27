from fastapi import FastAPI

app = FastAPI(title="Dr Wasif WhatsApp Bot")


@app.get("/healthz")
def healthz():
    return {"ok": True}

