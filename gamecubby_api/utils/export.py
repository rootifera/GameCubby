from sqlalchemy.orm import Session
from ..models.game import Game as GameModel
from .game_query import GAME_SCHEMA_LOAD_OPTIONS, games_to_schemas
import csv
import io
import json
import pandas as pd
from fastapi.responses import Response


def export_games_as_dicts(db: Session) -> list[dict]:
    games = db.query(GameModel).options(*GAME_SCHEMA_LOAD_OPTIONS).all()
    # location_path has always been empty in exports; keep the output identical.
    return [g.model_dump() for g in games_to_schemas(db, games, with_location_path=False)]


def export_games_as_json(db: Session) -> Response:
    data = export_games_as_dicts(db)
    # The whole export is already in memory, so send it as one body. (Streaming a
    # StringIO yields one chunk per line: ~100k tiny chunks for an indented export.)
    body = json.dumps(data, ensure_ascii=False, indent=2)

    return Response(
        body,
        media_type="application/json",
        headers={
            "Content-Disposition": "attachment; filename=games.json"
        }
    )

def export_games_as_csv(db: Session) -> Response:
    data = export_games_as_dicts(db)

    if not data:
        data = [{}]

    headers = list(data[0].keys())
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerows(data)

    return Response(output.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=games.csv"
    })


def export_games_as_excel(db: Session) -> Response:
    data = export_games_as_dicts(db)
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Games")

    return Response(output.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
        "Content-Disposition": "attachment; filename=games.xlsx"
    })
