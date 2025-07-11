
from app.common.constants import UserActivity
from app.common.helpers import activity
from app.common.database import users
from sqlalchemy.orm import Session
from fastapi import (
    HTTPException,
    APIRouter,
    Depends,
    Query
)

import hashlib
import app

router = APIRouter()

def ensure_coins(user_id: int) -> None:
    if not app.session.redis.exists(f'bancho:coins:{user_id}'):
        set_coins(user_id, 10)

def get_coins(user_id: int) -> int:
    value = app.session.redis.get(f'bancho:coins:{user_id}')
    return int(value or 0)

def set_coins(user_id: int, value: int) -> None:
    app.session.redis.set(f'bancho:coins:{user_id}', value)

def update_coins(user_id: int, value: int) -> None:
    app.session.redis.incrby(f'bancho:coins:{user_id}', value)

@router.get('/coins.php')
def osu_coins(
    session: Session = Depends(app.session.database.yield_session),
    checksum: str = Query(..., alias='cs'),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    count: int = Query(..., alias='c'),
    action: str = Query(...)
) -> str:
    if not (player := users.fetch_by_name(username, session=session)):
        raise HTTPException(401)
    
    if not app.utils.check_password(password, player.bcrypt):
        raise HTTPException(401)

    # Set the player's coins to 10, if they don't exist
    ensure_coins(player.id)

    checksum_string = f"{username}{count}osuycoins".encode()
    coins_checksum = hashlib.md5(checksum_string).hexdigest()
    amount = 0

    if coins_checksum != checksum:
        raise HTTPException(400)

    if action in ("earn", "use"):
        amount = -1 if action == "use" else 1
        update_coins(player.id, amount)

    if action == "recharge":
        amount = 99
        set_coins(player.id, amount)

    activity_type = (
        UserActivity.OsuCoinsUsed
        if action == "use" else
        UserActivity.OsuCoinsReceived
    )
    coins = get_coins(player.id)

    # Submit to activity queue
    activity.submit(
        player.id, None,
        activity_type,
        {
            'username': player.name,
            'amount': amount,
            'coins': coins
        },
        is_hidden=True,
        session=session
    )
    
    return str(coins)
