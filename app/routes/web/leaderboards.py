
from __future__ import annotations
from typing import Callable

from sqlalchemy.orm import Session
from datetime import datetime
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Request,
    Depends,
    Query
)

from app.common.database import DBBeatmapset, DBScore, DBUser
from app.common.database.repositories import (
    relationships,
    beatmaps,
    scores,
    users
)

from app.common.cache import status
from app.common.constants import (
    SubmissionStatus,
    LegacyStatus,
    RankingType,
    GameMode,
    Mods
)

import config
import utils
import app

router = APIRouter()

def resolve_beatmapset(
    beatmap_file: str,
    beatmap_hash: str,
    session: Session
) -> DBBeatmapset | None:
    if beatmap := beatmaps.fetch_by_file(beatmap_file, session):
        return beatmap

    if beatmap := beatmaps.fetch_by_checksum(beatmap_hash, session):
        return beatmap

def resolve_player(
    username: str | None,
    user_id: int | None,
    password: str | None,
    session: Session
) -> DBUser | None:
    if user_id:
        user = users.fetch_by_id(
            user_id,
            session=session
        )

        if not user:
            raise HTTPException(401)

        return user

    if not username or not password:
        raise HTTPException(401)

    user = users.fetch_by_name(
        username,
        session=session
    )

    if not user:
        raise HTTPException(401)

    if not utils.check_password(password, user.bcrypt):
        raise HTTPException(401)

    return user

def resolve_mods(score: DBScore) -> int:
    mods = Mods(score.mods)

    if Mods.Nightcore in mods and Mods.DoubleTime not in mods:
        # NC requires DT to be present
        mods |= Mods.DoubleTime

    return mods.value

def integer_boolean(parameter: str) -> Callable:
    async def wrapper(request: Request) -> bool:
        query = request.query_params.get(parameter, '0')
        return query == '1'
    return wrapper

def score_string(score: DBScore, index: int, request_version: int = 1) -> str:
    return '|'.join([
        str(score.id),
        str(score.user.name),
        str(score.total_score),
        str(score.max_combo),
        str(score.n50),
        str(score.n100),
        str(score.n300),
        str(score.nMiss),
        str(score.nKatu),
        str(score.nGeki),
        str(score.perfect),
        str(resolve_mods(score)),
        str(score.user_id),
        str(index),
        # This was changed to a unix timestamp in request version 2
        (
            str(score.submitted_at) if request_version <= 1 else
            str(round(score.submitted_at.timestamp()))
        ),
        # "Has Replay", added in request version 4
        str(1)
    ])

def score_string_legacy(score: DBScore, seperator: str = '|') -> str:
    return seperator.join([
        str(score.id),
        str(score.user.name),
        str(score.total_score),
        str(score.max_combo),
        str(score.n50),
        str(score.n100),
        str(score.n300),
        str(score.nMiss),
        str(score.nKatu),
        str(score.nGeki),
        str(score.perfect),
        str(resolve_mods(score)),
        str(score.user_id),
        str(score.user_id), # Avatar Filename
        str(score.submitted_at)
    ])

@router.get('/osu-osz2-getscores.php')
def get_scores(
    session: Session = Depends(app.session.database.yield_session),
    skip_scores: bool = Depends(integer_boolean('s')),
    ranking_type: RankingType | None = Query(1, alias='v'),
    request_version: int | None = Query(1, alias='vv'),
    username: str | None = Query(None, alias='us'),
    password: str | None = Query(None, alias='ha'),
    user_id: int | None = Query(None, alias='u'),
    beatmap_hash: str = Query(..., alias='c'),
    beatmap_file: str = Query(..., alias='f'),
    mode: GameMode = Query(..., alias='m'),
    osz_hash: str = Query(..., alias='h'),
    set_id: int = Query(..., alias='i'),
    mods: int | None = Query(0),
):
    player = resolve_player(
        username,
        user_id,
        password,
        session=session
    )

    if not status.exists(player.id):
        raise HTTPException(401)

    users.update(
        player.id,
        {'latest_activity': datetime.now()},
        session=session
    )

    if not (beatmap := resolve_beatmapset(beatmap_file, beatmap_hash, session)):
        return Response('-1|false') # Not Submitted

    if beatmap.md5 != beatmap_hash:
        return Response('1|false') # Update Available

    if not ranking_type:
        ranking_type = RankingType.Top

    submission_status = SubmissionStatus.from_database(
        beatmap.status,
        request_version
    )

    # TODO: has_osz is used to check if the osz file is still up to date
    #       However, we would have to implement a few more endpoints to
    #       make this work properly.
    has_osz = False

    # Fetch score count
    personal_best = None
    score_count = 0
    friends = None

    if ranking_type == RankingType.Friends:
        friends = relationships.fetch_target_ids(
            player.id,
            session=session
        )

    if beatmap.is_ranked:
        personal_best = scores.fetch_personal_best(
            beatmap.id,
            player.id,
            mode.value,
            mods if ranking_type == RankingType.SelectedMod else None,
            session
        )

        if personal_best:
            score_count = scores.fetch_count_beatmap(
                beatmap.id,
                mode.value,
                mods=mods
                    if ranking_type == RankingType.SelectedMod
                    else None,
                country=player.country
                    if ranking_type == RankingType.Country
                    else None,
                friends=friends
                    if ranking_type == RankingType.Friends
                    else None,
                session=session
            )

            if ranking_type == RankingType.Friends:
                score_count += 1

    # NOTE: In request version 3, the submission status
    #       swapped the Qualified and Ranked status
    if request_version > 2:
        submission_status = {
            SubmissionStatus.Ranked: SubmissionStatus.Qualified,
            SubmissionStatus.Qualified: SubmissionStatus.Ranked
        }.get(submission_status, submission_status)

    response = []

    # Beatmap Info
    response.append(
        '|'.join([
            str(submission_status.value),
            str(has_osz),
            str(beatmap.id),
            str(beatmap.set_id),
            str(score_count)
        ])
    )

    # Global offset
    response.append(f'{beatmap.beatmapset.offset}')

    # Title (Example: https://i.imgur.com/BofeZ2z.png)
    response.append(beatmap.beatmapset.display_title)

    # NOTE: This was actually used for user ratings, but
    #       we are using the new star ratings instead.
    response.append(f'{beatmap.diff}')

    if skip_scores or not beatmap.is_ranked:
        return Response('\n'.join(response))

    if personal_best:
        index = scores.fetch_score_index(
            player.id,
            beatmap.id,
            mode.value,
            mods           if ranking_type == RankingType.SelectedMod else None,
            friends        if ranking_type == RankingType.Friends     else None,
            player.country if ranking_type == RankingType.Country     else None,
            session
        )

        response.append(
            score_string(personal_best, index, request_version)
        )
    else:
        response.append('')

    top_scores = []

    if ranking_type == RankingType.Top:
        top_scores = scores.fetch_range_scores(
            beatmap.id,
            mode=mode.value,
            limit=config.SCORE_RESPONSE_LIMIT,
            session=session
        )

    elif ranking_type == RankingType.Country:
        top_scores = scores.fetch_range_scores_country(
            beatmap.id,
            mode=mode.value,
            country=player.country,
            limit=config.SCORE_RESPONSE_LIMIT,
            session=session
        )

    elif ranking_type == RankingType.Friends:
        top_scores = scores.fetch_range_scores_friends(
            beatmap.id,
            mode=mode.value,
            friends=friends,
            limit=config.SCORE_RESPONSE_LIMIT,
            session=session
        )

    elif ranking_type == RankingType.SelectedMod:
        top_scores = scores.fetch_range_scores_mods(
            beatmap.id,
            mode=mode.value,
            mods=mods,
            limit=config.SCORE_RESPONSE_LIMIT,
            session=session
        )

    for index, score in enumerate(top_scores):
        response.append(
            score_string(score, index, request_version)
        )

    return Response('\n'.join(response))

@router.get('/osu-getscores6.php')
def legacy_scores(
    session: Session = Depends(app.session.database.yield_session),
    skip_scores: bool = Depends(integer_boolean('s')),
    mode: GameMode = Query(GameMode.Osu, alias='m'),
    beatmap_hash: str = Query(..., alias='c'),
    beatmap_file: str = Query(..., alias='f'),
    player_id: int = Query(..., alias='u')
):
    if not status.exists(player_id):
        raise HTTPException(401)

    if not (player := users.fetch_by_id(player_id, session=session)):
        raise HTTPException(401)

    if not (beatmap := resolve_beatmapset(beatmap_file, beatmap_hash, session)):
        return Response('-1') # Not Submitted

    if beatmap.md5 != beatmap_hash:
        return Response('1') # Update Available

    users.update(
        player.id,
        {'latest_activity': datetime.now()},
        session=session
    )

    response = []
    submission_status = SubmissionStatus.from_database_legacy(beatmap.status)

    response.append(f'{submission_status.value}')
    response.append(f'{beatmap.beatmapset.offset}')

    # Title (Example: https://i.imgur.com/BofeZ2z.png)
    response.append(beatmap.beatmapset.display_title)

    # NOTE: This was actually used for user ratings, but
    #       we are using the new star ratings instead
    response.append(f'{beatmap.diff}')

    if skip_scores or not beatmap.is_ranked:
        return Response('\n'.join(response))

    personal_best = scores.fetch_personal_best(
        beatmap.id,
        player.id,
        mode.value,
        session=session
    )

    if personal_best:
        index = scores.fetch_score_index(
            player.id,
            beatmap.id,
            mode.value,
            session=session
        )

        response.append(
            score_string(personal_best, index)
        )
    else:
        response.append('')

    top_scores = scores.fetch_range_scores(
        beatmap.id,
        mode=mode.value,
        limit=config.SCORE_RESPONSE_LIMIT,
        session=session
    )

    for index, score in enumerate(top_scores):
        response.append(
            score_string(score, index)
        )

    return Response('\n'.join(response))

@router.get('/osu-getscores5.php')
def legacy_scores_no_ratings(
    session: Session = Depends(app.session.database.yield_session),
    skip_scores: bool = Depends(integer_boolean('s')),
    mode: GameMode = Query(GameMode.Osu, alias='m'),
    beatmap_hash: str = Query(..., alias='c'),
    beatmap_file: str = Query(..., alias='f'),
    player_id: int = Query(..., alias='u')
):
    if not status.exists(player_id):
        raise HTTPException(401)

    if not (player := users.fetch_by_id(player_id, session=session)):
        raise HTTPException(401)

    if not (beatmap := resolve_beatmapset(beatmap_file, beatmap_hash, session)):
        return Response('-1') # Not Submitted

    if beatmap.md5 != beatmap_hash:
        return Response('1') # Update Available

    user_status = status.get(player.id)

    if user_status.mode != mode:
        # Assign new mode to player
        app.session.events.submit(
            'user_update',
            user_id=player.id,
            mode=mode.value
        )

    users.update(
        player.id,
        {'latest_activity': datetime.now()},
        session=session
    )

    response = []
    submission_status = SubmissionStatus.from_database_legacy(beatmap.status)

    response.append(f'{submission_status.value}')
    response.append(f'{beatmap.beatmapset.offset}')

    # Title (Example: https://i.imgur.com/BofeZ2z.png)
    response.append(beatmap.beatmapset.display_title)

    if skip_scores or not beatmap.is_ranked:
        return Response('\n'.join(response))

    personal_best = scores.fetch_personal_best(
        beatmap.id,
        player.id,
        mode.value,
        session=session
    )

    if personal_best:
        index = scores.fetch_score_index(
            player.id,
            beatmap.id,
            mode.value,
            session=session
        )

        response.append(
            score_string(personal_best, index)
        )
    else:
        response.append('')

    top_scores = scores.fetch_range_scores(
        beatmap.id,
        mode=mode.value,
        limit=config.SCORE_RESPONSE_LIMIT,
        session=session
    )

    for index, score in enumerate(top_scores):
        response.append(
            score_string(score, index)
        )

    return Response('\n'.join(response))

@router.get('/osu-getscores4.php')
def legacy_scores_no_beatmap_data(
    session: Session = Depends(app.session.database.yield_session),
    skip_scores: bool = Depends(integer_boolean('s')),
    beatmap_hash: str = Query(..., alias='c'),
    beatmap_file: str = Query(..., alias='f'),
    player_id: int = Query(..., alias='u')
):
    if not status.exists(player_id):
        raise HTTPException(401)

    if not (player := users.fetch_by_id(player_id, session=session)):
        raise HTTPException(401)

    if not (beatmap := resolve_beatmapset(beatmap_file, beatmap_hash, session)):
        return Response('-1') # Not Submitted

    if beatmap.md5 != beatmap_hash:
        return Response('1') # Update Available

    user_status = status.get(player.id)
    mode = GameMode.Osu

    if user_status.mode != mode:
        # Assign new mode to player
        app.session.events.submit(
            'user_update',
            user_id=player.id,
            mode=mode.value
        )

    users.update(
        player.id,
        {'latest_activity': datetime.now()},
        session=session
    )

    response = []
    submission_status = SubmissionStatus.from_database_legacy(beatmap.status)

    # Status
    response.append(f'{submission_status.value}')

    if skip_scores or not beatmap.is_ranked:
        return Response('\n'.join(response))

    personal_best = scores.fetch_personal_best(
        beatmap.id,
        player.id,
        mode.value,
        session=session
    )

    if personal_best:
        index = scores.fetch_score_index(
            player.id,
            beatmap.id,
            mode.value,
            session=session
        )

        response.append(
            score_string(personal_best, index)
        )
    else:
        response.append('')

    top_scores = scores.fetch_range_scores(
        beatmap.id,
        mode=mode.value,
        limit=config.SCORE_RESPONSE_LIMIT,
        session=session
    )

    for index, score in enumerate(top_scores):
        response.append(
            score_string(score, index)
        )

    return Response('\n'.join(response))

@router.get('/osu-getscores3.php')
def legacy_scores_no_personal_best(
    session: Session = Depends(app.session.database.yield_session),
    skip_scores: bool = Depends(integer_boolean('s')),
    beatmap_hash: str = Query(..., alias='c'),
    beatmap_file: str = Query(..., alias='f')
):
    if not (beatmap := resolve_beatmapset(beatmap_file, beatmap_hash, session)):
        return Response('-1') # Not Submitted

    if beatmap.md5 != beatmap_hash:
        return Response('1') # Update Available

    response = []
    submission_status = SubmissionStatus.from_database_legacy(beatmap.status)

    # Status
    response.append(f'{submission_status.value}')

    if skip_scores or not beatmap.is_ranked:
        return Response('\n'.join(response))

    top_scores = scores.fetch_range_scores(
        beatmap.id,
        mode=GameMode.Osu.value,
        limit=config.SCORE_RESPONSE_LIMIT,
        session=session
    )

    for score in top_scores:
        response.append(
            score_string_legacy(score)
        )

    return Response('\n'.join(response))

@router.get('/osu-getscores2.php')
def legacy_scores_status_change(
    session: Session = Depends(app.session.database.yield_session),
    skip_scores: bool = Depends(integer_boolean('s')),
    beatmap_hash: str = Query(..., alias='c'),
    beatmap_file: str = Query(..., alias='f')
):
    # TODO: /osu-getscores2.php response format is different in some versions
    #       One method would be to check the client version over the cache

    if not (beatmap := resolve_beatmapset(beatmap_file, beatmap_hash, session)):
        return Response('-1') # Not Submitted

    if beatmap.md5 != beatmap_hash:
        return Response('1') # Update Available

    response = []
    submission_status = LegacyStatus.from_database(beatmap.status)

    # Status
    if submission_status <= SubmissionStatus.Unknown:
        response.append(f'{submission_status.value}')

    if skip_scores or not beatmap.is_ranked:
        return Response('\n'.join(response))

    top_scores = scores.fetch_range_scores(
        beatmap.id,
        mode=GameMode.Osu.value,
        limit=config.SCORE_RESPONSE_LIMIT,
        session=session
    )

    for score in top_scores:
        response.append(
            score_string_legacy(score)
        )

    return Response('\n'.join(response))

@router.get('/osu-getscores.php')
def legacy_scores_no_status(
    session: Session = Depends(app.session.database.yield_session),
    beatmap_hash: str = Query(..., alias='c')
):
    if not (beatmap := beatmaps.fetch_by_checksum(beatmap_hash, session)):
        return Response('-1') # Not Submitted

    top_scores = scores.fetch_range_scores(
        beatmap.id,
        mode=GameMode.Osu.value,
        limit=config.SCORE_RESPONSE_LIMIT,
        session=session
    )

    return Response('\n'.join([
        score_string_legacy(score, seperator=':')
        for score in top_scores
    ]))
