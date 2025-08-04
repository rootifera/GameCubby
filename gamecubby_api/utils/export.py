from sqlalchemy.orm import Session
from ..models.game import Game as GameModel
from ..schemas.game import Game
import csv
import io
import json
import pandas as pd
from fastapi.responses import StreamingResponse


def export_games_as_dicts(db: Session) -> list[dict]:
    games = db.query(GameModel).all()
    return [Game.model_validate(game).model_dump() for game in games]


def export_games_as_json(db: Session) -> StreamingResponse:
    data = export_games_as_dicts(db)
    output = io.StringIO()
    json.dump(data, output, ensure_ascii=False, indent=2)
    output.seek(0)

    return StreamingResponse(
        output,
        media_type="application/json",
        headers={
            "Content-Disposition": "attachment; filename=games.json"
        }
    )

def export_games_as_csv(db: Session) -> StreamingResponse:
    data = export_games_as_dicts(db)

    if not data:
        data = [{}]

    headers = list(data[0].keys())
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerows(data)
    output.seek(0)

    return StreamingResponse(output, media_type="text/csv", headers={
        "Content-Disposition": "attachment; filename=games.csv"
    })


def export_games_as_excel(db: Session) -> StreamingResponse:
    data = export_games_as_dicts(db)
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Games")
    output.seek(0)

    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={
        "Content-Disposition": "attachment; filename=games.xlsx"
    })
