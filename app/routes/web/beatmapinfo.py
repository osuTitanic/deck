
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session, selectinload
from pydantic import BaseModel
from typing import List, Tuple

from app.common.database import DBBeatmap, DBScore
from app.common.constants import Grade
from app.common.database import users
from app.common.cache import status
from app import utils

import app

router = APIRouter()

class BeatmapInfoRequestForm(BaseModel):
    Filenames: list[str]
    Ids: list[int]

@router.post("/osu-getbeatmapinfo.php")
def get_beatmap_info(
    info: BeatmapInfoRequestForm,
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias="u"),
    password: str = Query(..., alias="h"),
) -> bytes:
    if not (player := users.fetch_by_name(username, session=session)):
        raise HTTPException(401)

    if not utils.check_password(password, player.bcrypt):
        raise HTTPException(401)

    if not status.exists(player.id):
        raise HTTPException(401)

    maps: List[Tuple[int, DBBeatmap]] = []
    total_maps = len(info.Filenames) + len(info.Ids)

    if total_maps <= 0 or total_maps > 100:
        return b""

    app.session.logger.info(
        f'<{player.name} ({player.id})> -> Got {total_maps} beatmap requests.'
    )

    filename_beatmaps = session.query(DBBeatmap) \
        .options(selectinload(DBBeatmap.beatmapset)) \
        .filter(DBBeatmap.filename.in_(info.Filenames)) \
        .all()

    found_beatmaps = {
        beatmap.filename:beatmap
        for beatmap in filename_beatmaps
    }

    for index, filename in enumerate(info.Filenames):
        if filename not in found_beatmaps:
            continue

        # The client will identify the beatmaps by their index
        # in the "beatmapInfoSendList" array for the filenames
        maps.append((
            index,
            found_beatmaps[filename]
        ))

    id_beatmaps = session.query(DBBeatmap) \
        .options(selectinload(DBBeatmap.beatmapset)) \
        .filter(DBBeatmap.id.in_(info.Ids)) \
        .all()

    for beatmap in id_beatmaps:
        # For the ids, the client doesn't require the index
        # and we can just set it to -1, so that it will lookup
        # the beatmap by its id
        maps.append((
            -1,
            beatmap
        ))

    # Create beatmap response
    beatmap_infos: List[str] = []

    for index, beatmap in maps:
        if beatmap.status <= -3:
            # Not submitted
            continue

        response_status = {
            -3: -1, # Inactive: Not submitted
            -2: 0,  # Graveyard: Pending
            -1: 0,  # WIP: Pending
             0: 0,  # Pending: Pending
        }.get(beatmap.status, beatmap.status)

        # Get personal best in every mode for this beatmap
        grades = {
            0: Grade.N,
            1: Grade.N,
            2: Grade.N,
            3: Grade.N
        }

        for mode in range(4):
            grade = session.query(DBScore.grade) \
                .filter(DBScore.beatmap_id == beatmap.id) \
                .filter(DBScore.user_id == player.id) \
                .filter(DBScore.mode == mode) \
                .filter(DBScore.status_pp == 3) \
                .filter(DBScore.hidden == False) \
                .scalar()

            if grade:
                grades[mode] = Grade[grade]

        beatmap_infos.append(
            "|".join(map(str, [
                index,
                beatmap.id,
                beatmap.beatmapset.id,
                beatmap.md5,
                response_status,
                *grades.values()
            ]))
        )

    app.session.logger.info(
        f'Sending reply with {len(beatmap_infos)} beatmaps to {player.name}'
    )

    return "\n".join(beatmap_infos).encode()

