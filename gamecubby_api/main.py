from fastapi import FastAPI
from .routers import igdb

from dotenv import load_dotenv
load_dotenv()

app = FastAPI()

app.include_router(igdb.router, prefix="/igdb")

@app.get("/")
def read_root():
    return {"message": "GameCubby API is alive!"}
