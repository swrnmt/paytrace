from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.incidents import router as incidents_router

app = FastAPI(title="PayTrace API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://paytrace-three.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(incidents_router)


@app.get("/")
def root():
    return {"status": "PayTrace API is running"}