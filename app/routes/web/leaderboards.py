
from __future__ import annotations

from datetime import datetime
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Query
)

from app.common.cache import status
from app.common.database.repositories import (
    relationships,
    beatmaps,
    scores,
    users
)

from app.common.constants import (
    SubmissionStatus,
    LegacyStatus,
    RankingType,
    GameMode
)

import config
import bcrypt
import utils
import app

router = APIRouter()

@router.get('/osu-osz2-getscores.php')
def get_scores(
    request_version: int | None = Query(1, alias='vv'),
    username: str | None = Query(None, alias='us'),
    password: str | None = Query(None, alias='ha'),
    ranking_type: int | None = Query(1, alias='v'),
    user_id: int | None = Query(None, alias='u'),
    beatmap_hash: str = Query(..., alias='c'),
    beatmap_file: str = Query(..., alias='f'),
    skip_scores: str = Query(..., alias='s'),
    osz_hash: str = Query(..., alias='h'),
    set_id: int = Query(..., alias='i'),
    mode: int = Query(..., alias='m'),
    mods: int | None = Query(0),
):
    with app.session.database.managed_session() as session:
        try:
            ranking_type = RankingType(ranking_type)
            skip_scores = skip_scores == '1'
            mode = GameMode(mode)
        except ValueError:
            raise HTTPException(400, 'https://pbs.twimg.com/media/Dqnn54dVYAAVuki.jpg')

        if username:
            if not (player := users.fetch_by_name(username, session)):
                raise HTTPException(401)

            if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
                raise HTTPException(401)
        else:
            if not user_id:
                raise HTTPException(401)

            if not (player := users.fetch_by_id(user_id, session)):
                raise HTTPException(401)

        if not status.exists(player.id):
            raise HTTPException(401)

        # Update latest activity
        users.update(player.id, {'latest_activity': datetime.now()}, session)

        if not (beatmap := beatmaps.fetch_by_file(beatmap_file, session)):
            # Search for beatmap hash as backup
            if not (beatmap := beatmaps.fetch_by_checksum(beatmap_hash, session)):
                return Response('-1|false') # Not Submitted

        if beatmap.md5 != beatmap_hash:
            return Response('1|false') # Update Available

        if not ranking_type:
            ranking_type = RankingType.Top

        response = []

        submission_status = SubmissionStatus.from_database(beatmap.status)

        # TODO: has_osz is used to check if the osz file is still up to date
        # But I think this is unused tho...
        has_osz = False

        # Fetch score count

        personal_best = None
        score_count = 0
        friends = None

        if ranking_type == RankingType.Friends:
            friends = relationships.fetch_target_ids(player.id, session)

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

        if (request_version > 2):
            # NOTE: In request version 3, the submission status is changed
            #       Qualified: 4
            #       Ranked: 2

            if submission_status == SubmissionStatus.Ranked:
                submission_status = SubmissionStatus.EditableCutoff

            elif submission_status == SubmissionStatus.EditableCutoff:
                submission_status = SubmissionStatus.Ranked

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

        if skip_scores or not beatmap.is_ranked:
            return Response('\n'.join(response))

        # Offset
        response.append('0')

        # Title
        # Example: https://i.imgur.com/BofeZ2z.png
        # TODO: Title Configuration?
        response.append(
            '|'.join(
                [(
                    '[bold:0,size:20]' +
                    beatmap.beatmapset.artist
                    if beatmap.beatmapset.artist
                    else ''
                ),
                (
                    '[]' +
                    beatmap.beatmapset.title
                    if beatmap.beatmapset.title
                    else ''
                )]
            )
        )

        # response.append(str(
        #     ratings.fetch_average(beatmap.md5),
        #     session
        # ))

        # NOTE: This was actually used for ratings, but
        #       we are using the new star ratings instead
        response.append(str(
            beatmap.diff
        ))

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
                utils.score_string(personal_best, index)
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

        else:
            raise HTTPException(400, 'https://pbs.twimg.com/media/Dqnn54dVYAAVuki.jpg')

        for index, score in enumerate(top_scores):
            response.append(
                utils.score_string(score, index, request_version)
            )

        return Response('\n'.join(response))

@router.get('/osu-getscores6.php')
def legacy_scores(
    beatmap_hash: str = Query(..., alias='c'),
    beatmap_file: str = Query(..., alias='f'),
    skip_scores: str = Query(..., alias='s'),
    player_id: int = Query(..., alias='u'),
    mode: int = Query(0, alias='m')
):
    try:
        skip_scores = skip_scores == '1'
        mode = GameMode(mode)
    except ValueError:
        raise HTTPException(400, 'https://pbs.twimg.com/media/Dqnn54dVYAAVuki.jpg')

    if not status.exists(player_id):
        raise HTTPException(401)

    with app.session.database.managed_session() as session:
        if not (player := users.fetch_by_id(player_id, session)):
            raise HTTPException(401)

        if not (beatmap := beatmaps.fetch_by_file(beatmap_file, session)):
            # Search for beatmap hash as backup
            if not (beatmap := beatmaps.fetch_by_checksum(beatmap_hash, session)):
                return Response('-1') # Not Submitted

        if beatmap.md5 != beatmap_hash:
            return Response('1') # Update Available

        # Update latest activity
        users.update(player.id, {'latest_activity': datetime.now()}, session)

        response = []

        submission_status = SubmissionStatus.from_database(beatmap.status)

        # Status
        response.append(str(submission_status.value))

        if skip_scores or not beatmap.is_ranked:
            return Response('\n'.join(response))

        # Offset
        response.append('0')

        # Title
        # Example: https://i.imgur.com/BofeZ2z.png
        # TODO: Title Configuration?
        response.append(
            '|'.join(
                [(
                    '[bold:0,size:20]' +
                    beatmap.beatmapset.artist
                    if beatmap.beatmapset.artist
                    else ''
                ),
                (
                    '[]' +
                    beatmap.beatmapset.title
                    if beatmap.beatmapset.title
                    else ''
                )]
            )
        )

        # response.append(str(
        #     ratings.fetch_average(beatmap.md5)
        # ))

        # NOTE: This was actually used for ratings, but
        #       we are using the new star ratings instead
        response.append(str(
            beatmap.diff
        ))

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
                utils.score_string(personal_best, index)
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
                utils.score_string(score, index)
            )

        return Response('\n'.join(response))

@router.get('/osu-getscores5.php')
def legacy_scores_no_ratings(
    beatmap_hash: str = Query(..., alias='c'),
    beatmap_file: str = Query(..., alias='f'),
    skip_scores: str = Query(..., alias='s'),
    player_id: int = Query(..., alias='u'),
    mode: int = Query(0, alias='m')
):
    try:
        skip_scores = skip_scores == '1'
        mode = GameMode(mode)
    except ValueError:
        raise HTTPException(400, 'https://pbs.twimg.com/media/Dqnn54dVYAAVuki.jpg')

    if not status.exists(player_id):
        raise HTTPException(401)

    with app.session.database.managed_session() as session:
        if not (player := users.fetch_by_id(player_id, session)):
            raise HTTPException(401)

        if not (beatmap := beatmaps.fetch_by_file(beatmap_file, session)):
            # Search for beatmap hash as backup
            if not (beatmap := beatmaps.fetch_by_checksum(beatmap_hash, session)):
                return Response('-1') # Not Submitted

        if beatmap.md5 != beatmap_hash:
            return Response('1') # Update Available

        # Update latest activity
        users.update(player.id, {'latest_activity': datetime.now()}, session)

        response = []

        submission_status = SubmissionStatus.from_database(beatmap.status)

        # Status
        response.append(str(submission_status.value))

        if skip_scores or not beatmap.is_ranked:
            return Response('\n'.join(response))

        # Offset
        response.append('0')

        # Title
        # Example: https://i.imgur.com/BofeZ2z.png
        # TODO: Title Configuration?
        response.append(
            '|'.join(
                [(
                    '[bold:0,size:20]' +
                    beatmap.beatmapset.artist
                    if beatmap.beatmapset.artist
                    else ''
                ),
                (
                    '[]' +
                    beatmap.beatmapset.title
                    if beatmap.beatmapset.title
                    else ''
                )]
            )
        )

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
                utils.score_string(personal_best, index)
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
                utils.score_string(score, index)
            )

        return Response('\n'.join(response))

@router.get('/osu-getscores4.php')
def legacy_scores_no_beatmap_data(
    beatmap_hash: str = Query(..., alias='c'),
    beatmap_file: str = Query(..., alias='f'),
    skip_scores: str = Query(..., alias='s'),
    player_id: int = Query(..., alias='u')
):
    skip_scores = skip_scores == '1'
    mode = GameMode.Osu

    if not status.exists(player_id):
        raise HTTPException(401)

    with app.session.database.managed_session() as session:
        if not (player := users.fetch_by_id(player_id, session)):
            raise HTTPException(401)

        if not (beatmap := beatmaps.fetch_by_file(beatmap_file, session)):
            # Search for beatmap hash as backup
            if not (beatmap := beatmaps.fetch_by_checksum(beatmap_hash, session)):
                return Response('-1') # Not Submitted

        if beatmap.md5 != beatmap_hash:
            return Response('1') # Update Available

        # Update latest activity
        users.update(player.id, {'latest_activity': datetime.now()}, session)

        response = []

        submission_status = SubmissionStatus.from_database(beatmap.status)

        # Status
        response.append(str(submission_status.value))

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
                utils.score_string(personal_best, index)
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
                utils.score_string(score, index)
            )

        return Response('\n'.join(response))

@router.get('/osu-getscores3.php')
def legacy_scores_no_personal_best(
    beatmap_hash: str = Query(..., alias='c'),
    beatmap_file: str = Query(..., alias='f'),
    skip_scores: str = Query(..., alias='s')
):
    skip_scores = skip_scores == '1'
    mode = GameMode.Osu

    with app.session.database.managed_session() as session:
        if not (beatmap := beatmaps.fetch_by_file(beatmap_file, session)):
            # Search for beatmap hash as backup
            if not (beatmap := beatmaps.fetch_by_checksum(beatmap_hash, session)):
                return Response('-1') # Not Submitted

        if beatmap.md5 != beatmap_hash:
            return Response('1') # Update Available

        response = []

        submission_status = SubmissionStatus.from_database(beatmap.status)

        # Status
        response.append(str(submission_status.value))

        if skip_scores or not beatmap.is_ranked:
            return Response('\n'.join(response))

        top_scores = scores.fetch_range_scores(
            beatmap.id,
            mode=mode.value,
            limit=config.SCORE_RESPONSE_LIMIT,
            session=session
        )

        for score in top_scores:
            response.append(
                utils.score_string_legacy(score)
            )

        return Response('\n'.join(response))

@router.get('/osu-getscores2.php')
def legacy_scores_status_change(
    beatmap_hash: str = Query(..., alias='c'),
    beatmap_file: str = Query(..., alias='f'),
    skip_scores: str | None = Query(None, alias='s')
):
    # TODO: /osu-getscores2.php response format is different in some versions
    #       One method would be to check the client version over the cache

    skip_scores = skip_scores == '1'
    mode = GameMode.Osu

    with app.session.database.managed_session() as session:
        if not (beatmap := beatmaps.fetch_by_file(beatmap_file, session)):
            # Search for beatmap hash as backup
            if not (beatmap := beatmaps.fetch_by_checksum(beatmap_hash, session)):
                return Response('-1') # Not Submitted

        if beatmap.md5 != beatmap_hash:
            return Response('1') # Update Available

        response = []

        submission_status = LegacyStatus.from_database(beatmap.status)

        # Status
        if submission_status <= SubmissionStatus.Unknown:
            response.append(str(submission_status.value))

        if skip_scores or not beatmap.is_ranked:
            return Response('\n'.join(response))

        top_scores = scores.fetch_range_scores(
            beatmap.id,
            mode=mode.value,
            limit=config.SCORE_RESPONSE_LIMIT,
            session=session
        )

        for score in top_scores:
            response.append(
                utils.score_string_legacy(score)
            )

        return Response('\n'.join(response))

# TODO: osu-getscores.php
