
from fastapi import (
    HTTPException,
    UploadFile,
    APIRouter,
    Response,
    Request,
    File,
    Form
)

from typing import Optional

from app.objects import Score, ClientHash
from app.constants import Mod

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
            raise HTTPException(400, 'error: invalid submission key')

    client_hash = ClientHash.from_string(client_hash)

    replay = (await replay.read()) if replay else None

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
    
    # TODO: Update stats
    # TODO: Client response

    instance.commit()

    return RecursionError('error: no')
