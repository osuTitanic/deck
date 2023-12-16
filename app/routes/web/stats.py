
from app.common.database.repositories import users
from app.common.cache import status, leaderboards

from fastapi import APIRouter, HTTPException, Query

import hashlib
import app

router = APIRouter()

@router.get('/osu-statoth.php')
def legacy_user_stats(
    username: str = Query(..., alias='u'),
    checksum: str = Query(..., alias='c')
):
    app.session.logger.info(f'Got stats request for "{username}" ({checksum})')

    # Validate checksum
    checksum_match = hashlib.md5(f'{username}prettyplease!!!'.encode()).hexdigest()

    if checksum != checksum_match:
        app.session.logger.warning('Failed to send stats: Checksum mismatch!')
        raise HTTPException(400)

    if not (user_id := users.fetch_user_id(username)):
        app.session.logger.warning('Failed to send stats: User not found!')
        raise HTTPException(404)

    if not (s := status.get(user_id)):
        app.session.logger.warning('Failed to send stats: User not online!')
        raise HTTPException(404)

    current_rank = leaderboards.global_rank(user_id, s.mode.value)
    current_acc = leaderboards.accuracy(user_id, s.mode.value)
    current_score = leaderboards.score(user_id, s.mode.value)

    return '|'.join([
        str(current_score),
        str(round(current_acc, 5)),
        str(current_rank),
        str(user_id) # Avatar Filename
    ])
