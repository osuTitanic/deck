
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from app.common.database.repositories import users
from app.common.cache import leaderboards
from app import utils

import hashlib
import app

router = APIRouter()

@router.get('/osu-statoth.php')
@router.get('/osu-stat.php')
def legacy_user_stats(
    username: str = Query(..., alias='u'),
    checksum: str | None = Query(None, alias='c'),
    password: str | None = Query(None, alias='p')
) -> str:
    app.session.logger.info(f'Got stats request for "{username}" ({checksum})')

    if not (password or checksum):
        app.session.logger.warning('Failed to send stats: Missing checksum!')
        raise HTTPException(401)

    if checksum:
        # Validate checksum
        checksum_match = hashlib.md5(f'{username}prettyplease!!!'.encode()).hexdigest()

        if checksum != checksum_match:
            app.session.logger.warning('Failed to send stats: Checksum mismatch!')
            raise HTTPException(400)

    if not (user_id := users.fetch_user_id(username)):
        app.session.logger.warning('Failed to send stats: User not found!')
        raise HTTPException(404)

    # TODO: Check if user is online?
    current_rank = leaderboards.global_rank(user_id, mode=0)
    current_acc = leaderboards.accuracy(user_id, mode=0)
    current_score = leaderboards.score(user_id, mode=0)

    return '|'.join([
        str(current_score),
        str(current_acc),
        "", # TODO
        "", # TODO
        str(current_rank),
        str(user_id) # Avatar Filename
    ])
