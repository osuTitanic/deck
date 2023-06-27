
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
from asyncio import run
from copy import copy

from app.objects import Score, ClientHash, ScoreStatus, Grade
from app.common.objects import DBStats
from app.constants import Mod

import hashlib
import base64
import config
import bcrypt
import utils
import app

router = APIRouter()

@router.post('/osu-submit-modular.php')
def score_submission(
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
    form = run(request.form())

    score_data = form.getlist('score')[0]

    if iv:
        try:
            iv = base64.b64decode(iv)
            client_hash = utils.decrypt_string(client_hash, iv)
            fun_spoiler = utils.decrypt_string(fun_spoiler, iv)
            score_data  = utils.decrypt_string(score_data, iv)
            processes   = utils.decrypt_string(processes, iv)
        except UnicodeDecodeError:
            raise HTTPException(400, 'error: invalid submission key')

    client_hash = ClientHash.from_string(client_hash)

    replay = run(replay.read()) if replay else None

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

    if score.beatmap.status < 0:
        return Response('error: beatmap')

    if not app.session.cache.user_exists(player.id):
        return Response('error: no')

    if score.passed:
        if not replay:
            app.session.logger.warning(
                f'"{score.username}" submitted score without replay.'
            )
            # TODO: Restrict player
            return Response('error: no')

        replay_hash = hashlib.md5(replay).hexdigest()
        duplicate_score = app.session.database.score_by_checksum(replay_hash)

        if duplicate_score:
            if duplicate_score.user.name != score.username:
                app.session.logger.warning(
                    f'"{score.username}" submitted duplicate replay in score submission.'
                )
                # TODO: Restrict player
                return Response('error: no')

            return Response('error: no')

    bancho_hash = app.session.cache.get_user(player.id)[b'client_hash']

    if bancho_hash.decode() != client_hash.string:
        app.session.logger.warning(
            f'"{score.username}" submitted score with client hash mismatch.'
        )
        # TODO: Restrict player
        return Response('error: no')

    # TODO: Check for invalid mods
    # TODO: More anticheat stuff

    # What is FreeModAllowed?
    if Mod.FreeModAllowed in score.enabled_mods:
        score.enabled_mods = score.enabled_mods & ~Mod.FreeModAllowed

    object = score.to_database()
    object.client_hash = str(client_hash)
    object.screenshot  = screenshot
    object.processes   = processes

    if not config.ALLOW_RELAX and score.relaxing:
        object.status = -1

    instance = app.session.database.session
    instance.add(object)
    instance.flush()

    if score.passed:
        # TODO: Only save replays of scores in top 50
        app.session.storage.upload_replay(object.id, replay)

    instance.commit()

    score.beatmap.playcount += 1
    score.beatmap.passcount += 1 if score.passed else 0

    score.session.commit()

    stats: DBStats = instance.query(DBStats) \
                .filter(DBStats.user_id == player.id) \
                .filter(DBStats.mode == score.play_mode.value) \
                .first()

    old_stats = copy(stats)

    stats.playcount += 1
    stats.playtime += score.beatmap.total_length  \
                      if score.passed else \
                      score.failtime / 1000
    stats.tscore += score.total_score
    stats.total_hits += score.total_hits

    instance.flush()

    # TODO: Update plays

    if not config.ALLOW_RELAX and score.relaxing:
        return Response('error: no')

    previous_grade = None
    grade = None

    if score.beatmap.is_ranked:
        score_count = app.session.database.score_count(score.user.id)
        top_scores = app.session.database.top_scores(score.user.id)

        if score.status == ScoreStatus.Best:
            if score.personal_best:
                # Remove old score
                stats.rscore -= score.personal_best.total_score

                previous_grade = score.personal_best.grade
                grade = score.grade if score.grade != score.personal_best.grade else None
            else:
                grade = score.grade

            stats.rscore += score.total_score

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

    # Update grades

    try:
        if grade:
            grade = Grade(grade).name.lower()

            grade_attribute = getattr(stats, f'{grade}_count')
            grade_attribute += 1

            if previous_grade:
                previous_grade = Grade(previous_grade).name.lower()

                grade_attribute = getattr(stats, f'{previous_grade.lower()}_count')
                grade_attribute -= 1
    except AttributeError:
        pass

    instance.commit()

    # TODO: Achievements
    # TODO: Client response

    return RecursionError('error: no')
