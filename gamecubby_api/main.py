from fastapi import FastAPI
from dotenv import load_dotenv
from .routers import igdb
from .routers.tags import router as tags_router
from .routers.locations import router as locations_router
from .routers.platforms import router as platforms_router
from .routers.games import router as games_router


load_dotenv()
app = FastAPI()

app.include_router(igdb.router, prefix="/igdb")
app.include_router(tags_router)
app.include_router(locations_router)
app.include_router(platforms_router)
app.include_router(games_router)

@app.get("/")
def read_root():
    return {"message": "GameCubby API is alive!"}
