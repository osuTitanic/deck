
from fastapi import APIRouter, HTTPException, Query, Depends
from sqlalchemy.orm import Session, load_only, selectinload
from typing import Dict, List, Tuple
from pydantic import BaseModel

from app.common.database import DBBeatmap, DBBeatmapset, DBScore
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
        .options(*beatmap_info_load()) \
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
        .options(*beatmap_info_load()) \
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

    grade_lookup = fetch_grade_lookup(
        player.id,
        [beatmap.id for _, beatmap in maps],
        session
    )

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
            0: 0,   # Pending: Pending
        }.get(beatmap.status, beatmap.status)

        grades = grade_lookup.get(
            beatmap.id,
            default_grades()
        )

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

def default_grades() -> Dict[int, Grade]:
    return {
        0: Grade.N,
        1: Grade.N,
        2: Grade.N,
        3: Grade.N
    }

def beatmap_info_load():
    return (
        load_only(
            DBBeatmap.id,
            DBBeatmap.set_id,
            DBBeatmap.status,
            DBBeatmap.md5,
            DBBeatmap.filename
        ),
        selectinload(DBBeatmap.beatmapset).load_only(
            DBBeatmapset.id
        )
    )

def fetch_grade_lookup(
    user_id: int,
    beatmap_ids: List[int],
    session: Session
) -> Dict[int, Dict[int, Grade]]:
    if not beatmap_ids:
        return {}

    rows = session.query(
        DBScore.beatmap_id,
        DBScore.mode,
        DBScore.grade
    ) \
        .filter(DBScore.beatmap_id.in_(beatmap_ids)) \
        .filter(DBScore.user_id == user_id) \
        .filter(DBScore.mode.in_((0, 1, 2, 3))) \
        .filter(DBScore.status_pp == 3) \
        .filter(DBScore.hidden == False) \
        .all()

    grade_lookup = {}

    for beatmap_id, mode, grade in rows:
        grades = grade_lookup.setdefault(
            beatmap_id,
            default_grades()
        )
        grades[mode] = Grade[grade]

    return grade_lookup
