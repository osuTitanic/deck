
from starlette.datastructures import FormData
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Request,
    Depends,
    Query,
    Form
)

from datetime import datetime, timedelta
from typing import Optional, Tuple, List, Callable
from copy import copy

from app.common.database import DBStats, DBScore, DBUser
from app import achievements as AchievementManager
from app.objects import Score, ScoreStatus, Chart
from app.common.cache import leaderboards, status
from app.common.helpers import performance

from app.common.database.repositories import (
    achievements,
    histories,
    scores,
    plays,
    users
)

import hashlib
import base64
import config
import bcrypt
import utils
import app

router = APIRouter()

async def parse_score_data(request: Request) -> Score:
    """Parse the score submission request and return a score object"""
    query = request.query_params
    form = await request.form()

    if score_data := query.get('score'):
        # Legacy score was submitted
        failtime: Optional[str] = query.get('ft', 0)
        exited: Optional[str] = query.get('x', False)

        # Get replay
        if replay_file := form.get('score'):
            if replay_file.filename != 'replay':
                app.session.logger.warning(f'Got invalid replay name: {replay.filename}')
                raise HTTPException(400)

            replay = await replay_file.read()

        try:
            return Score.parse(
                score_data,
                replay,
                bool(exited),
                int(failtime)
            )
        except Exception as e:
            app.session.logger.error(
                f'Failed to parse score data: {e}',
                exc_info=e
            )
            raise HTTPException(400)

    # NOTE: The form data can contain two "score" sections, where
    #       one of them is the score data, and the other is the replay

    if not (score_form := form.getlist('score')):
        app.session.logger.warning(
            'Got score submission without score data!'
        )
        raise HTTPException(400)

    score_data = score_form[0]
    fun_spoiler = form.get('fs')
    client_hash = form.get('s')
    processes = form.get('pl')
    failtime = form.get('ft')
    exited = form.get('x')
    replay = None

    if len(score_form) > 1:
        # Replay data was provided
        replay = score_form[-1]

        if replay.filename != 'replay':
            app.session.logger.warning(f'Got invalid replay name: {replay.filename}')
            raise HTTPException(400)

        replay = await replay.read()

    if iv := form.get('iv'):
        # Score data is encrypted
        try:
            iv = base64.b64decode(iv)
            client_hash = utils.decrypt_string(client_hash, iv)
            fun_spoiler = utils.decrypt_string(fun_spoiler, iv)
            score_data  = utils.decrypt_string(score_data, iv)
            processes   = utils.decrypt_string(processes, iv)
        except UnicodeDecodeError as e:
            # Most likely an invalid score encryption key
            app.session.logger.warning(f'Could not decrypt score data: {e}')
            raise HTTPException(400)

    try:
        score = Score.parse(
            score_data,
            replay,
            bool(exited) if exited else None,
            int(failtime) if failtime else None
        )
    except Exception as e:
        app.session.logger.error(
            f'Failed to parse score data: {e}',
            exc_info=e
        )
        raise HTTPException(400)

    score.fun_spoiler = fun_spoiler
    score.client_hash = client_hash
    score.processes = processes
    return score

def perform_score_validation(score: Score, player: DBUser) -> Optional[Response]:
    """Validate the score submission requests and return an error if the validation fails"""
    if score.total_hits <= 0:
        # This could still be a false-positive
        app.session.logger.warning(
            f'"{score.username}" submitted score with total_hits <= 0.'
        )
        return Response('error: no')

    if score.passed:
        # Check for replay
        if not score.replay:
            app.session.logger.warning(
                f'"{score.username}" submitted score without replay.'
            )
            app.session.events.submit(
                'restrict',
                user_id=player.id,
                reason='Score submission without replay'
            )
            return Response('error: ban')

        # Check for duplicate score
        replay_hash = hashlib.md5(score.replay).hexdigest()
        duplicate_score = scores.fetch_by_replay_checksum(replay_hash)

        if duplicate_score:
            if duplicate_score.user_id != player.id:
                app.session.logger.warning(
                    f'"{score.username}" submitted duplicate replay in score submission ({duplicate_score.replay_md5}).'
                )
                app.session.events.submit(
                    'restrict',
                    user_id=player.id,
                    reason='Duplicate replay in score submission'
                )
                return Response('error: ban')

            app.session.logger.warning(
                f'"{score.username}" submitted duplicate replay from themselves ({duplicate_score.replay_md5}).'
            )

            return Response('error: no')

    if score.has_invalid_mods:
        app.session.logger.warning(
            f'"{score.username}" submitted score with invalid mods.'
        )
        app.session.events.submit(
            'restrict',
            user_id=player.id,
            reason='Invalid mods on score submission'
        )
        return Response('error: ban')

    # Check score submission "spam"
    if (recent_scores := scores.fetch_recent(player.id, score.play_mode.value, limit=5)):
        # NOTE: Client should normally submit scores in 8 second intervals.
        #       However, this can fail sometimes resulting in an instant ban...

        # I know this looks messy...
        submission_times = [
            # Get the time between score submissions
            (
                (
                    recent_scores[index - 1].submitted_at.timestamp()
                    if index != 0
                    else datetime.now().timestamp()
                ) - recent_score.submitted_at.timestamp()
            )
            # For every recent score
            for index, recent_score in enumerate(recent_scores)
            if index != (len(recent_scores) - 1)
        ]

        if len(submission_times) > 0:
            average_submission_time = (
                sum(submission_times) / len(submission_times)
            )

            if average_submission_time <= 8 and len(recent_scores) == 5:
                app.session.logger.warning(
                    f'"{score.username}" is spamming score submission.'
                )
                app.session.events.submit(
                    'restrict',
                    user_id=player.id,
                    reason='Spamming score submission'
                )
                return Response('error: ban')

    # TODO: Circleguard replay analysis
    # TODO: Client hash validation

def upload_replay(score: Score, score_id: int) -> None:
    if (score.passed and score.status > ScoreStatus.Exited):
        # Check replay size (10mb max)
        if len(score.replay) < 1e+7:
            score_rank = scores.fetch_score_index_by_id(
                mods=score.enabled_mods.value,
                beatmap_id=score.beatmap.id,
                mode=score.play_mode.value,
                score_id=score_id
            )

            # Replay will be cached temporarily and deleted after
            app.session.storage.cache_replay(
                score_id,
                score.replay
            )

            if score.beatmap.is_ranked and score.status > ScoreStatus.Submitted:
                # Check if score is inside the leaderboards
                if score_rank <= config.SCORE_RESPONSE_LIMIT:
                    app.session.storage.upload_replay(
                        score_id,
                        score.replay
                    )
    else:
        # Cache replay for
        app.session.storage.cache_replay(
            id=score_id,
            content=score.replay,
            time=timedelta(minutes=30)
        )

def update_stats(score: Score, player: DBUser) -> Tuple[DBStats, DBStats]:
    """Update the users and beatmaps stats. It will return the old & new stats for the user"""

    # Update beatmap stats
    score.beatmap.playcount += 1
    score.beatmap.passcount += 1 if score.passed else 0
    score.session.commit()

    # Update user stats
    stats: DBStats = score.session.query(DBStats) \
            .filter(DBStats.user_id == player.id) \
            .filter(DBStats.mode == score.play_mode.value) \
            .first()

    old_stats = copy(stats)

    stats.playcount += 1
    stats.playtime += score.beatmap.total_length \
                      if score.passed else \
                      score.failtime / 1000

    if score.status != ScoreStatus.Failed:
        stats.tscore += score.total_score
        stats.total_hits += score.total_hits

    score.session.commit()

    histories.update_plays(
        stats.user_id,
        stats.mode
    )

    plays.update(
        score.beatmap.filename,
        score.beatmap.id,
        score.user.id,
        score.beatmap.set_id,
    )

    best_scores = scores.fetch_best(
        user_id=score.user.id,
        mode=score.play_mode.value,
        exclude_approved=False
                         if config.APPROVED_MAP_REWARDS else
                         True
    )

    if score.beatmap.is_ranked and score.status == ScoreStatus.Best:
        # Update max combo
        if score.max_combo > stats.max_combo:
            stats.max_combo = score.max_combo

    if best_scores:
        # Update accuracy
        weighted_acc = sum(score.acc * 0.95**index for index, score in enumerate(best_scores))
        bonus_acc = 100.0 / (20 * (1 - 0.95 ** len(best_scores)))

        stats.acc = (weighted_acc * bonus_acc) / 100

        # Update performance
        weighted_pp = sum(score.pp * 0.95**index for index, score in enumerate(best_scores))
        bonus_pp = 416.6667 * (1 - 0.9994 ** len(best_scores))

        stats.pp = weighted_pp + bonus_pp

        # Update rscore
        stats.rscore = sum(
            score.total_score for score in best_scores
        )

        leaderboards.update(
            stats.user_id,
            stats.mode,
            stats.pp,
            stats.rscore,
            player.country.lower(),
            stats.tscore,
            stats.ppv1
        )

        stats.rank = leaderboards.global_rank(
            stats.user_id,
            stats.mode
        )

        grades = {}

        try:
            # Update grades
            for s in best_scores:
                grade = f'{s.grade.lower()}_count'
                grades[grade] = grades.get(grade, 0) + 1

            score.session.query(DBStats) \
                .filter(DBStats.user_id == score.user.id) \
                .filter(DBStats.mode == score.play_mode.value) \
                .update(grades)

            score.session.commit()
        except Exception as e:
            app.session.logger.error(
                'Failed to update user grades!',
                exc_info=e
            )

        if score.passed:
            # NOTE: ppv1 calculations take a while, since we need to
            #       fetch the rank for each score from the database.
            #       I am not sure if this is the best way to do it...
            app.session.executor.submit(
                update_ppv1,
                best_scores,
                stats,
                player.country
            )

    # Update preferred mode
    if player.preferred_mode != score.play_mode.value:
        recent_scores = scores.fetch_recent_top_scores(
            player.id,
            limit=15
        )

        if len({s.mode for s in recent_scores}) == 1:
            users.update(
                player.id,
                {'preferred_mode': score.play_mode.value}
            )

    return stats, old_stats

def update_ppv1(scores: DBScore, stats: DBStats, country: str):
    stats.ppv1 = performance.calculate_weighted_ppv1(scores)

    leaderboards.update(
        stats.user_id,
        stats.mode,
        stats.pp,
        stats.rscore,
        country,
        stats.tscore,
        stats.ppv1
    )

    histories.update_rank(
        stats,
        country
    )

@router.post('/osu-submit-modular.php')
def score_submission(
    flashlight_screenshot: Optional[bytes] = Form(None, alias='i'),
    legacy_password: Optional[str] = Query(None, alias='pass'),
    password: Optional[str] = Form(None, alias='pass'),
    score: Score = Depends(parse_score_data),
):
    password = legacy_password or password

    if not (player := score.user):
        return Response('error: nouser')

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        return Response('error: pass')

    if not player.activated:
        return Response('error: inactive')

    if player.restricted:
        return Response('error: ban')

    if not score.beatmap:
        return Response('error: beatmap')

    if not status.exists(player.id):
        # Let the client resend the request
        return Response('')

    users.update(
        player.id,
        {'latest_activity': datetime.now()}
    )

    if flashlight_screenshot:
        app.session.logger.warning(
            f"{player.name} submitted score with a flashlight screenshot!"
        )

    if (error := perform_score_validation(score, player)) != None:
        return error

    if score.beatmap.is_ranked:
        # Get old rank before submitting score
        old_rank = scores.fetch_score_index_by_id(
                    score.personal_best.id,
                    score.beatmap.id,
                    mode=score.play_mode.value
                   ) \
                if score.personal_best else 0

        # Submit to database
        score_object = score.to_database()
        score_object.client_hash = score.client_hash
        score_object.processes = score.processes
        score_object.bad_flags = score.flags

        # TODO: Remove processes list from database table

        if not config.ALLOW_RELAX and score.relaxing:
            score_object.status = -1

        score.session.add(score_object)
        score.session.flush()

        # Try to upload replay
        upload_replay(
            score,
            score_object.id
        )

        score.session.commit()

    new_stats, old_stats = update_stats(score, player)

    # Reload stats on bancho
    app.session.events.submit(
        'user_update',
        user_id=player.id
    )

    if not score.beatmap.is_ranked:
        score.session.close()
        return Response('error: beatmap')

    if not config.ALLOW_RELAX and score.relaxing:
        score.session.close()
        return Response('error: no')

    achievement_response: List[str] = []
    response: List[Chart] = []

    # TODO: Enable achievements for relax?
    if score.passed and not score.relaxing:
        unlocked_achievements = achievements.fetch_many(player.id)
        ignore_list = [a.filename for a in unlocked_achievements]

        new_achievements = AchievementManager.check(score_object, ignore_list)
        achievement_response = [a.filename for a in new_achievements]

        achievements.create_many(new_achievements, player.id)

    beatmap_rank = scores.fetch_score_index_by_tscore(
        score_object.total_score,
        score.beatmap.id,
        mode=score.play_mode.value
    )

    beatmapInfo = Chart()
    beatmapInfo['beatmapId'] = score.beatmap.id
    beatmapInfo['beatmapSetId'] = score.beatmap.set_id
    beatmapInfo['beatmapPlaycount'] = score.beatmap.playcount
    beatmapInfo['beatmapPasscount'] = score.beatmap.passcount
    beatmapInfo['approvedDate'] = score.beatmap.beatmapset.approved_at

    response.append(beatmapInfo)

    # TODO: Implement monthly charts

    overallChart = Chart()
    overallChart['chartId'] = 'overall'
    overallChart['chartName'] = 'Overall Ranking'
    overallChart['chartEndDate'] = ''
    overallChart['achievements'] = ' '.join(achievement_response)

    overallChart.entry('rank', old_stats.rank, new_stats.rank)
    overallChart.entry('rankedScore', old_stats.rscore, new_stats.rscore)
    overallChart.entry('totalScore', old_stats.tscore, new_stats.tscore)
    overallChart.entry('accuracy', round(old_stats.acc, 4), round(new_stats.acc, 4))
    overallChart.entry('playCount', old_stats.playcount, new_stats.playcount)

    overallChart['onlineScoreId']  = score_object.id
    overallChart['toNextRankUser'] = ''
    overallChart['toNextRank'] = '0'

    if score.beatmap.is_ranked:
        overallChart.entry(
            'beatmapRanking',
            old_rank,
            beatmap_rank
        )

        difference, next_user = leaderboards.player_above(
            player.id,
            score.play_mode.value
        )

        if difference > 0:
            overallChart['toNextRankUser'] = next_user
            overallChart['toNextRank'] = difference

    response.append(overallChart)

    app.session.logger.info(
        f'"{score.username}" submitted {"failed " if score.failtime else ""}score on {score.beatmap.full_name}'
    )

    score.session.close()

    # Send highlights on #announce
    if score.status == ScoreStatus.Best:
        app.session.executor.submit(
            app.highlights.check,
            score.user,
            new_stats,
            old_stats,
            score_object,
            beatmap_rank,
            old_rank
        )

    return Response('\n'.join([chart.get() for chart in response]))

@router.post('/osu-submit.php')
@router.post('/osu-submit-new.php')
def legacy_score_submission(
    password: Optional[str] = Query(None, alias='pass'),
    score: Score = Depends(parse_score_data)
):
    if not (player := score.user):
        raise HTTPException(401)

    if not bcrypt.checkpw(password.encode(), player.bcrypt.encode()):
        raise HTTPException(401)

    if not player.activated:
        raise HTTPException(401)

    if player.restricted:
        raise HTTPException(401)

    if not score.beatmap:
        raise HTTPException(404)

    if not status.exists(player.id):
        return Response('')

    users.update(player.id, {'latest_activity': datetime.now()})

    if (error := perform_score_validation(score, player)) != None:
        return error

    if score.beatmap.is_ranked:
        # Get old rank before submitting score
        old_rank = scores.fetch_score_index_by_id(
                    score.personal_best.id,
                    score.beatmap.id,
                    mode=score.play_mode.value
                   ) \
                if score.personal_best else 0

        # Submit to database
        score_object = score.to_database()
        score_object.client_hash = ''
        score_object.processes = '' # TODO: Remove this
        score_object.bad_flags = score.flags

        if not config.ALLOW_RELAX and score.relaxing:
            score_object.status = -1

        score.session.add(score_object)
        score.session.flush()

        # Try to upload replay
        upload_replay(
            score,
            score_object.id
        )

        score.session.commit()

    new_stats, old_stats = update_stats(score, player)

    if not score.beatmap.is_ranked:
        app.session.events.submit(
            'user_update',
            user_id=player.id
        )
        score.session.close()
        return

    if not config.ALLOW_RELAX and score.relaxing:
        app.session.events.submit(
            'user_update',
            user_id=player.id
        )
        score.session.close()
        return

    app.session.logger.info(
        f'"{score.username}" submitted {"failed " if score.failtime else ""}score on {score.beatmap.full_name}'
    )

    if not score.passed:
        app.session.events.submit(
            'user_update',
            user_id=player.id
        )
        score.session.close()
        return

    # TODO: This part seems to be taking a loooong time...?

    achievement_response: List[str] = []
    response: List[Chart] = []

    if not score.relaxing:
        unlocked_achievements = achievements.fetch_many(player.id)
        ignore_list = [a.filename for a in unlocked_achievements]

        new_achievements = AchievementManager.check(score_object, ignore_list)
        achievement_response = [a.filename for a in new_achievements]

        achievements.create_many(new_achievements, player.id)

    beatmap_rank = scores.fetch_score_index_by_id(
        score_object.id,
        score.beatmap.id,
        mode=score.play_mode.value
    )

    # Reload stats on bancho
    app.session.events.submit(
        'user_update',
        user_id=player.id
    )

    if score.status == ScoreStatus.Best:
        response.append(str(beatmap_rank))
    else:
        response.append('0')

    difference, next_user = leaderboards.player_above(
        player.id,
        score.play_mode.value
    )

    response.append(str(difference))
    response.append(' '.join(achievement_response))

    score.session.close()

    # Send highlights on #announce
    if score.status == ScoreStatus.Best:
        app.session.executor.submit(
            app.highlights.check,
            score.user,
            new_stats,
            old_stats,
            score_object,
            beatmap_rank,
            old_rank
        )

    return '\n'.join(response)
