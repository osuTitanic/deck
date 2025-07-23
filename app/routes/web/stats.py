
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

    avatar_checksum = resolve_avatar_checksum(user_id)
    current_rank = leaderboards.global_rank(user_id, mode=0)
    current_acc = leaderboards.accuracy(user_id, mode=0)
    current_score = leaderboards.score(user_id, mode=0)

    # Cap score to a signed 32-bit integer to prevent overflow
    current_score_capped = min(current_score, 2147483647)

    return '|'.join([
        f"{current_score_capped}",
        f"{current_acc}",
        f"{current_score}", # NOTE: This field is usually empty & unused
        f"{user_id}",       #       Same goes for this field
        f"{current_rank}",
        f"{user_id}_{avatar_checksum}.png" # Avatar Filename
    ])

def resolve_avatar_checksum(user_id: int) -> str:
    cached_checksum = app.session.redis.get(f'bancho:avatar_hash:{user_id}')

    if cached_checksum:
        return cached_checksum.decode('utf-8')

    checksum = (
        users.fetch_avatar_checksum(user_id) or "unknown"
    )

    app.session.redis.set(
        f'bancho:avatar_hash:{user_id}',
        checksum, ex=60 * 60 * 24
    )

    return checksum
