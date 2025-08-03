import os
import httpx
from sqlalchemy.orm import Session
from ..models.igdb_tag import IGDBTag
from ..utils.external import get_igdb_token, _get_igdb_credentials
from collections import defaultdict

TAG_TYPE_ENDPOINTS = {
    0: "themes",
    2: "keywords",
}



async def upsert_igdb_tags(db: Session, tag_numbers: list[int]) -> list[IGDBTag]:
    if not tag_numbers:
        return []

    tag_groups = defaultdict(set)
    for tag in tag_numbers:
        tag_type = tag >> 28
        object_id = tag & 0x0FFFFFFF
        if tag_type in TAG_TYPE_ENDPOINTS:
            tag_groups[tag_type].add(object_id)

    existing_tags = db.query(IGDBTag).filter(IGDBTag.id.in_(tag_numbers)).all()
    existing_map = {tag.id: tag for tag in existing_tags}
    new_tags = []

    client_id, _ = _get_igdb_credentials(db)
    token = await get_igdb_token()
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {token}"
    }

    for tag_type, ids in tag_groups.items():
        endpoint = TAG_TYPE_ENDPOINTS[tag_type]
        url = f"https://api.igdb.com/v4/{endpoint}"
        query = f"fields id,name; where id = ({','.join(str(i) for i in ids)});"

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=headers, data=query)
        resp.raise_for_status()
        results = resp.json()

        for obj in results:
            object_id = obj["id"]
            tag_number = (tag_type << 28) | object_id
            if tag_number in existing_map:
                continue
            tag = IGDBTag(id=tag_number, name=obj["name"])
            db.add(tag)
            db.flush()
            existing_map[tag_number] = tag
            new_tags.append(tag)

    db.commit()
    return [existing_map[tag] for tag in tag_numbers if tag in existing_map]