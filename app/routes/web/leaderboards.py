
from typing import Optional
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Query
)

from app.constants import (
    SubmissionStatus,
    RankingType,
    Mode
)

import config
import bcrypt
import utils
import app

router = APIRouter()

@router.get('/osu-osz2-getscores.php')
def get_scores(
    username: Optional[str] = Query(None, alias='us'),
    password: Optional[str] = Query(None, alias='ha'),
    ranking_type: Optional[int] = Query(1, alias='v'),
    user_id: Optional[int] = Query(None, alias='u'),
    beatmap_hash: str = Query(..., alias='c'),
    beatmap_file: str = Query(..., alias='f'),
    get_scores: int = Query(..., alias='s'),
    osz_hash: str = Query(..., alias='h'),
    set_id: int = Query(..., alias='i'),
    mode: int = Query(..., alias='m'),
    mods: Optional[int] = Query(0)
):
    try:
        ranking_type = RankingType(ranking_type)
        mode = Mode(mode)
    except ValueError:
        raise HTTPException(400, 'https://pbs.twimg.com/media/Dqnn54dVYAAVuki.jpg')

    if username:
        if not (player := app.session.database.user_by_name(username)):
            raise HTTPException(401)

        if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
            raise HTTPException(401)
    else:
        if not user_id:
            raise HTTPException(401)

        if not (player := app.session.database.user_by_id(user_id)):
            raise HTTPException(401)

    if not app.session.cache.user_exists(player.id):
        raise HTTPException(401)

    if not (beatmap := app.session.database.beatmap_by_file(beatmap_file)):
        return Response('-1|false')

    if beatmap.md5 != beatmap_hash:
        return Response('1|false')

    if not ranking_type:
        ranking_type = RankingType.Top

    response = []

    submission_status = SubmissionStatus.from_db(beatmap.status)
    has_osz = False # TODO

    # Beatmap Info
    response.append(
        '|'.join([
            str(submission_status.value),
            str(has_osz),
            str(beatmap.id),
            str(beatmap.set_id),
            str(0)
        ])
    )

    # Offset
    response.append('0')

    # Title
    # Example: https://i.imgur.com/BofeZ2z.png
    # TODO: Title Configuration?
    response.append(
        '|'.join(
            [
                '[bold:0,size:20]' +
                beatmap.beatmapset.artist,
                '[]' +
                beatmap.beatmapset.title
            ]
        )
    )

    ratings = app.session.database.ratings(beatmap.md5)
    response.append(
        str(sum(ratings) / len(ratings)) if ratings else '0'
    )

    personal_best = app.session.database.personal_best(
        beatmap.id,
        player.id,
        mode.value,
        mods if ranking_type == RankingType.SelectedMod else None
    )

    friends = [
        rel.target_id
        for rel in app.session.database.relationships(player.id)
        if rel.status == 0
    ]

    if personal_best:
        index = app.session.database.score_index(
            player.id,
            beatmap.id,
            mode.value,
            mods           if ranking_type == RankingType.SelectedMod else None,
            friends        if ranking_type == RankingType.Friends     else None,
            player.country if ranking_type == RankingType.Country     else None
        )

        response.append(
            utils.score_string(personal_best, index)
        )
    else:
        response.append('')

    scores = []

    if ranking_type == RankingType.Top:
        scores = app.session.database.range_scores(
            beatmap.id,
            mode=mode.value,
            limit=config.SCORE_RESPONSE_LIMIT
        )

    elif ranking_type == RankingType.Country:
        scores = app.session.database.range_scores_country(
            beatmap.id,
            mode=mode.value,
            country=player.country,
            limit=config.SCORE_RESPONSE_LIMIT
        )

    elif ranking_type == RankingType.Friends:
        scores = app.session.database.range_scores_friends(
            beatmap.id,
            mode=mode.value,
            friends=friends,
            limit=config.SCORE_RESPONSE_LIMIT
        )

    elif ranking_type == RankingType.SelectedMod:
        scores = app.session.database.range_scores_mods(
            beatmap.id,
            mode=mode.value,
            mods=mods,
            limit=config.SCORE_RESPONSE_LIMIT
        )

    else:
        raise HTTPException(400, 'https://pbs.twimg.com/media/Dqnn54dVYAAVuki.jpg')

    for index, score in enumerate(scores):
        response.append(
            utils.score_string(score, index)
        )

    return Response('\n'.join(response))

@router.get('/osu-getscores6.php')
def legacy_scores(
    beatmap_hash: str = Query(..., alias='c'),
    beatmap_file: str = Query(..., alias='f'),
    get_scores: int = Query(..., alias='s'),
    user_id: int = Query(..., alias='u'),
    mode: int = Query(..., alias='m')
):
    try:
        mode = Mode(mode)
    except ValueError:
        raise HTTPException(400, 'https://pbs.twimg.com/media/Dqnn54dVYAAVuki.jpg')

    if not app.session.cache.user_exists(user_id):
        raise HTTPException(401)

    if not (player := app.session.database.user_by_id(user_id)):
        raise HTTPException(401)

    if not (beatmap := app.session.database.beatmap_by_file(beatmap_file)):
        return Response('-1')

    if beatmap.md5 != beatmap_hash:
        return Response('1')

    response = []

    submission_status = SubmissionStatus.from_db(beatmap.status)

    # Status
    response.append(str(submission_status.value))

    # Offset
    response.append('0')

    # Title
    # Example: https://i.imgur.com/BofeZ2z.png
    # TODO: Title Configuration?
    response.append(
        '|'.join([
            '[bold:0,size:20]' +
            beatmap.beatmapset.artist,
            '[]' +
            beatmap.beatmapset.title
        ])
    )

    ratings = app.session.database.ratings(beatmap.md5)
    response.append(
        str(sum(ratings) / len(ratings)) if ratings else '0'
    )

    personal_best = app.session.database.personal_best(
        beatmap.id,
        player.id,
        mode.value
    )

    if personal_best:
        index = app.session.database.score_index(
            player.id,
            beatmap.id,
            mode.value
        )

        response.append(
            utils.score_string(personal_best, index)
        )
    else:
        response.append('')

    scores = app.session.database.range_scores(
        beatmap.id,
        mode=mode.value,
        limit=config.SCORE_RESPONSE_LIMIT
    )

    for index, score in enumerate(scores):
        response.append(
            utils.score_string(score, index)
        )

    return Response('\n'.join(response))
