
from app.common.database import DBBeatmapset, DBUser
from app.common.constants import DisplayMode
from app.common.cache import status
from app.common import officer
from app.common.database import (
    beatmapsets,
    beatmaps,
    users,
    posts
)

from sqlalchemy.orm import Session
from fastapi import (
    HTTPException,
    APIRouter,
    Depends,
    Query
)

import app

router = APIRouter()

def online_beatmap(set: DBBeatmapset, post_id: int = 0) -> str:
    versions = ",".join(
        [f"{beatmap.version}@{beatmap.mode}" for beatmap in set.beatmaps]
    )

    ratings = [
        r.rating for r in set.ratings
    ]

    average_rating = (
        sum(ratings) / len(ratings)
        if ratings else 0
    )

    return "|".join([
        f'{set.id} {set.artist} - {set.title}.osz',
        set.artist  if set.artist else "",
        set.title   if set.title else "",
        set.creator if set.creator else "",
        set.status,
        str(average_rating),
        str(set.last_update),
        str(set.id),
        str(set.topic_id or 0),
        str(int(set.has_video)),
        str(int(set.has_storyboard)),
        str(set.osz_filesize),
        str(set.osz_filesize_novideo),
        versions,
        str(post_id or 0),
    ])

def update_osz_filesize(set_id: int, has_video: bool = False) -> None:
    updates = {}

    if has_video:
        updates['osz_filesize_novideo'] = get_osz_size(
            set_id,
            no_video=True
        )

    updates['osz_filesize'] = get_osz_size(
        set_id,
        no_video=False
    )

    beatmapsets.update(set_id, updates)

def get_osz_size(set_id: int, no_video: bool = False) -> int:
    r = app.session.requests.head(
        f'https://osu.direct/api/d/{set_id}'
        f'{"noVideo=" if no_video else ""}'
    )

    if not r.ok:
        app.session.logger.error(
            f"Failed to get osz size: {r.status_code}"
        )
        return 0

    if not (filesize := r.headers.get('content-length')):
        app.session.logger.error(
            "Failed to get osz size: content-length header missing"
        )
        return 0

    return int(filesize)

@router.get('/osu-search.php')
def search(
    session: Session = Depends(app.session.database.yield_session),
    legacy_password: str | None = Query(None, alias='c'),
    page_offset: int | None = Query(None, alias='p'),
    username: str | None = Query(None, alias='u'),
    password: str | None = Query(None, alias='h'),
    display_mode: int = Query(4, alias='r'),
    query: str = Query(..., alias='q'),
    mode: int = Query(-1, alias='m')
) -> str:
    supports_page_offset = page_offset is not None
    page_offset = page_offset or 0
    player = None

    # Skip authentication for old clients
    if legacy_password or password:
        if not (player := users.fetch_by_name(username, session=session)):
            return '-1\nFailed to authenticate user'

        if not app.utils.check_password(password or legacy_password, player.bcrypt):
            return '-1\nFailed to authenticate user'

        if not status.exists(player.id):
            return '-1\nNot connected to bancho'

        if not player.is_supporter:
            return "-1\nWhy are you here?"

    if display_mode not in DisplayMode._value2member_map_:
        return "-1\nInvalid display mode"

    display_mode = DisplayMode(display_mode)

    if len(query) < 2:
        return "-1\nQuery is too short."

    app.session.logger.info(
        f'Got osu!direct search request: "{query}" '
        f'from "{player}"'
    )

    response = []

    try:
        results = beatmapsets.search(
            query,
            player.id if player else 0,
            display_mode,
            page_offset * 100,
            mode,
            session
        )

        if not supports_page_offset:
            response.append(str(
                len(results)
            ))

        else:
            response.append(str(
                len(results)
                if len(results) < 100 else 101
            ))

        for set in results:
            if set.topic_id:
                post_id = posts.fetch_initial_post_id(set.topic_id, session)
                response.append(online_beatmap(set, post_id))
                continue

            response.append(online_beatmap(set))
    except Exception as e:
        officer.call(f'Failed to execute search.', exc_info=e)
        return "-1\nServer error. Please try again!"

    return "\n".join(response)

@router.get('/osu-search-set.php')
def pickup_info(
    session: Session = Depends(app.session.database.yield_session),
    beatmap_id: int | None = Query(None, alias='b'),
    topic_id: int | None = Query(None, alias='t'),
    checksum: str | None = Query(None, alias='c'),
    post_id: int | None = Query(None, alias='p'),
    set_id: int | None = Query(None, alias='s'),
    username: str | None = Query(None, alias='u'),
    password: str | None = Query(None, alias='h'),
) -> str:
    beatmapset: DBBeatmapset | None = None
    player: DBUser | None = None

    # Skip authentication for old clients
    if username and password:
        if not (player := users.fetch_by_name(username, session=session)):
            raise HTTPException(401)

        if not app.utils.check_password(password, player.bcrypt):
            raise HTTPException(401)

        if not player.is_supporter:
            raise HTTPException(401)

    if set_id:
        beatmapset = beatmapsets.fetch_one(set_id, session)

    if beatmap_id:
        beatmap = beatmaps.fetch_by_id(beatmap_id, session)
        beatmapset = beatmap.beatmapset if beatmap else None

    if checksum:
        beatmap = beatmaps.fetch_by_checksum(checksum, session)
        beatmapset = beatmap.beatmapset if beatmap else None

    if post_id:
        topic_id = posts.fetch_topic_id(post_id, session)

    if topic_id:
        beatmapset = beatmapsets.fetch_by_topic(topic_id, session)

    if not beatmapset:
        app.session.logger.warning("osu!direct pickup request failed: Not found")
        raise HTTPException(404)

    if beatmapset.status == -3:
        # Beatmap was deleted or has not been submitted yet
        raise HTTPException(404)

    app.session.logger.info(
        f'{player} -> '
        f'Got osu!direct pickup request for: "{beatmapset.full_name}".'
    )

    if not beatmapset.osz_filesize:
        update_osz_filesize(
            beatmapset.id,
            beatmapset.has_video
        )

    return online_beatmap(
        beatmapset,
        posts.fetch_initial_post_id(beatmapset.topic_id, session)
    )
