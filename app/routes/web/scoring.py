
from fastapi import (
    HTTPException,
    UploadFile,
    APIRouter,
    Response,
    Request,
    File,
    Form
)

from typing import Optional, List
from threading import Thread
from copy import copy

from app.objects import Score, ClientHash, ScoreStatus, Chart
from app.common.objects import DBStats, DBScore
from app.services.anticheat import Anticheat
from app.constants import Mod, Grade
from app import achievements

import hashlib
import base64
import config
import bcrypt
import utils
import app

router = APIRouter()

@router.post('/osu-submit-modular.php')
async def score_submission(
    request: Request,
    iv: Optional[str] = Form(None),
    password: str = Form(..., alias='pass'),
    client_hash: str = Form(..., alias='s'),
    exited: Optional[bool] = Form(None, alias='x'),
    failtime: Optional[int] = Form(None, alias='ft'),
    processes: Optional[str] = Form(None, alias='pl'),
    fun_spoiler: Optional[str] = Form(None, alias='fs'),
    screenshot: Optional[bytes] = Form(None, alias='i'),
    replay: Optional[UploadFile] = File(None, alias='score')
):
    form = await request.form()

    score_data = form.getlist('score')[0]

    if iv:
        try:
            iv = base64.b64decode(iv)
            client_hash = utils.decrypt_string(client_hash, iv)
            fun_spoiler = utils.decrypt_string(fun_spoiler, iv)
            score_data  = utils.decrypt_string(score_data, iv)
            processes   = utils.decrypt_string(processes, iv)
        except UnicodeDecodeError:
            raise HTTPException(400, 'invalid submission key')

    client_hash = ClientHash.from_string(client_hash)

    replay = await replay.read() if replay else None

    score = Score.parse(
        score_data,
        replay,
        exited,
        failtime
    )

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

    if not app.session.cache.user_exists(player.id):
        # Client will resend the request
        return Response('')

    app.session.database.update_latest_activity(player.id)

    if score.passed:
        # Check for replay

        if not replay:
            app.session.logger.warning(
                f'"{score.username}" submitted score without replay.'
            )
            utils.submit_to_queue(
                type='restrict',
                data={
                    'user_id': score.user.id,
                    'reason': 'Score submission without replay.'
                }
            )
            return Response('error: ban')

        # Check for duplicate score

        replay_hash = hashlib.md5(replay).hexdigest()
        duplicate_score = app.session.database.score_by_checksum(replay_hash)

        if duplicate_score:
            if duplicate_score.user.name != score.username:
                app.session.logger.warning(
                    f'"{score.username}" submitted duplicate replay in score submission ({duplicate_score.replay_md5}).'
                )
                utils.submit_to_queue(
                    type='restrict',
                    data={
                        'user_id': score.user.id,
                        'reason': 'Duplicate replay in score submission'
                    }
                )
                return Response('error: ban')

            app.session.logger.warning(
                f'"{score.username}" submitted duplicate replay from themselves ({duplicate_score.replay_md5}).'
            )

            return Response('error: no')

    # Validate client hash

    bancho_hash = app.session.cache.get_user(player.id)[b'client_hash']

    if bancho_hash.decode() != client_hash.string:
        app.session.logger.warning(
            f'"{score.username}" submitted score with client hash mismatch.'
        )
        utils.submit_to_queue(
            type='restrict',
            data={
                'user_id': score.user.id,
                'reason': 'Score submission with client hash mismatch'
            }
        )
        return Response('error: ban')

    # Check for invalid mods

    if score.has_invalid_mods:
        app.session.logger.warning(
            f'"{score.username}" submitted score with invalid mods.'
        )
        utils.submit_to_queue(
            type='restrict',
            data={
                'user_id': score.user.id,
                'reason': 'Invalid mods on score submission'
            }
        )
        return Response('error: ban')

    # Check client flags

    if score.flags:
        app.session.logger.warning(
            f'"{score.username}" submitted score with bad flags: {score.flags}.'
        )

        # The "SpeedHackDetected" flag can be a false positive
        # especially on pc's with a lot of lag
        if score.flags > 2:
            utils.submit_to_queue(
                type='restrict',
                data={
                    'user_id': score.user.id,
                    'reason': f'Submitted score with bad flags ({score.flags.value})'
                }
            )
            return Response('error: ban')

    # What is FreeModAllowed?
    if Mod.FreeModAllowed in score.enabled_mods:
        score.enabled_mods = score.enabled_mods & ~Mod.FreeModAllowed

    # This fixes the keymods
    if Mod.keyMod in score.enabled_mods:
        score.enabled_mods = score.enabled_mods & ~Mod.keyMod

    # Submit to database

    score_object = score.to_database()
    score_object.client_hash = str(client_hash)
    score_object.screenshot  = screenshot
    score_object.processes   = processes
    score_object.bad_flags   = score.flags

    if not config.ALLOW_RELAX and score.relaxing:
        score_object.status = -1

    instance = app.session.database.session
    instance.add(score_object)
    instance.flush()

    # Upload replay

    if score.passed:
        if score.status.value > ScoreStatus.Submitted.value:
            score_rank = app.session.database.score_index_by_id(
                mods=score.enabled_mods.value,
                beatmap_id=score.beatmap.id,
                mode=score.play_mode.value,
                score_id=score_object.id
            )

            if score.beatmap.is_ranked:
                # Check if score is inside the leaderboards
                if score_rank <= config.SCORE_RESPONSE_LIMIT:
                    app.session.storage.upload_replay(score_object.id, replay)

    instance.commit()

    score.beatmap.playcount += 1
    score.beatmap.passcount += 1 if score.passed else 0

    score.session.commit()

    # Update user stats

    stats: DBStats = instance.query(DBStats) \
                .filter(DBStats.user_id == player.id) \
                .filter(DBStats.mode == score.play_mode.value) \
                .first()

    old_stats = copy(stats)

    stats.playcount += 1
    stats.playtime += score.beatmap.total_length  \
                      if score.passed else \
                      score.failtime / 1000

    if score.status != ScoreStatus.Failed:
        stats.tscore += score.total_score
        stats.total_hits += score.total_hits

    instance.commit()

    app.session.database.update_plays_history(
        stats.user_id,
        stats.mode
    )

    app.session.database.update_plays(
        score.beatmap.id,
        score.beatmap.filename,
        score.beatmap.set_id,
        score.user.id
    )

    if score.beatmap.status < 0:
        return Response('error: beatmap')

    if not config.ALLOW_RELAX and score.relaxing:
        return Response('error: no')

    previous_grade = None
    grade = None

    score_count = app.session.database.score_count(score.user.id, score.play_mode.value)
    top_scores = app.session.database.top_scores(
        user_id=score.user.id,
        mode=score.play_mode.value,
        exclude_approved=False
                         if config.APPROVED_MAP_REWARDS else
                         True
    )

    if score.beatmap.is_ranked:
        if score.status == ScoreStatus.Best:
            # Update grades
            if score.personal_best:
                previous_grade = Grade[score.personal_best.grade]
                grade = score.grade

                if previous_grade == grade:
                    previous_grade = None
                    grade = None

                # Remove old score
                if score.beatmap.awards_pp:
                    stats.rscore -= score.personal_best.total_score
            else:
                grade = score.grade

            stats.rscore += score.total_score

        # Update max combo

        max_combo_score = instance.query(DBScore) \
            .filter(DBScore.user_id == score.user.id) \
            .order_by(DBScore.max_combo.desc()) \
            .first()

        if max_combo_score:
            if score.max_combo > max_combo_score.max_combo:
                stats.max_combo = score.max_combo

    if score_count > 0:
        # Update accuracy

        total_acc = 0
        divide_total = 0

        for index, s in enumerate(top_scores):
            add = 0.95 ** index
            total_acc    += s.acc * add
            divide_total += add

        if divide_total != 0:
            stats.acc = total_acc / divide_total
        else:
            stats.acc = 0.0

        # Update performance

        weighted_pp = sum(score.pp * 0.95**index for index, score in enumerate(top_scores))
        bonus_pp = 416.6667 * (1 - 0.9994**score_count)

        stats.pp = weighted_pp + bonus_pp

        app.session.cache.update_leaderboards(stats)

        stats.rank = app.session.cache.get_global_rank(stats.user_id, stats.mode)

        instance.commit()

        if score.passed:
            app.session.database.update_rank_history(stats)

    # Update grades

    if grade:
        if grade != previous_grade:
            grade_name = f'{grade.name.lower()}_count'

            updates = {grade_name: getattr(DBStats, grade_name) + 1}

            if previous_grade:
                grade_name = f'{previous_grade.name.lower()}_count'

                updates.update(
                    {grade_name: getattr(DBStats, grade_name) - 1}
                )

            instance.query(DBStats) \
                    .filter(DBStats.user_id == score.user.id) \
                    .filter(DBStats.mode == score.play_mode.value) \
                    .update(updates)

    instance.commit()

    # Reload stats on bancho
    utils.submit_to_queue(
        type='user_update',
        data={
            'user_id': score.user.id
        }
    )

    beatmap_rank = app.session.database.score_index_by_id(
        score_object.id,
        score.beatmap.id,
        mode=score.play_mode.value
    )

    if score.status == ScoreStatus.Best:
        Thread(
            target=app.highlights.check,
            args=[
                score.user,
                stats,
                old_stats,
                score_object,
                beatmap_rank
            ],
            daemon=True
        ).start()

    # TODO: Update preferred mode

    achievement_response: List[str] = []
    response: List[Chart] = []

    if score.passed and not score.relaxing:
        unlocked_achievements = app.session.database.achievements(player.id)
        ignore_list = [a.filename for a in unlocked_achievements]

        new_achievements = achievements.check(score_object, ignore_list)
        achievement_response = [a.filename for a in new_achievements]

        app.session.database.add_achievements(new_achievements, player.id)

    beatmapInfo = Chart()
    beatmapInfo['beatmapId'] = score.beatmap.id
    beatmapInfo['beatmapSetId'] = score.beatmap.set_id
    beatmapInfo['beatmapPlaycount'] = score.beatmap.playcount
    beatmapInfo['beatmapPasscount'] = score.beatmap.passcount
    beatmapInfo['approvedDate'] = score.beatmap.beatmapset.approved_at

    response.append(beatmapInfo)

    # TODO: Implement monthly charts?

    overallChart = Chart()
    overallChart['chartId'] = 'overall'
    overallChart['chartName'] = 'Overall Ranking'
    overallChart['chartEndDate'] = ''
    overallChart['achievements'] = ' '.join(achievement_response)

    overallChart.entry('rank', old_stats.rank, stats.rank)
    overallChart.entry('rankedScore', old_stats.rscore, stats.rscore)
    overallChart.entry('totalScore', old_stats.tscore, stats.tscore)
    overallChart.entry('accuracy', round(old_stats.acc, 4), round(stats.acc, 4))
    overallChart.entry('playCount', old_stats.playcount, stats.playcount)

    overallChart['onlineScoreId']  = score_object.id
    overallChart['toNextRankUser'] = ''
    overallChart['toNextRank'] = '0'

    if score.beatmap.status > 0:
        old_rank = app.session.database.score_index_by_id(
                    score.personal_best.id,
                    score.beatmap.id,
                    mode=score.play_mode.value
                   ) \
                if score.personal_best else 0

        overallChart.entry(
            'beatmapRanking',
            old_rank,
            beatmap_rank
        )

        score_above = app.session.database.score_above(
            score.beatmap.id,
            score.play_mode.value,
            score.total_score
        )

        if score_above:
            overallChart['toNextRankUser'] = score_above.user.name
            overallChart['toNextRank'] = score_above.total_score - score.total_score

    response.append(overallChart)

    app.session.logger.info(
        f'"{score.username}" submitted {"failed " if score.failtime else ""}score on {score.beatmap.full_name}'
    )

    if config.CIRCLEGUARD_ENABLED:
        ac = Anticheat()

        Thread(
            target=ac.perform_checks,
            args=[score, score_object.id],
            daemon=True
        ).start()

    return Response('\n'.join([chart.get() for chart in response]))
