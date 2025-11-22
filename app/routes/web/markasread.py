
from fastapi import HTTPException, Response, APIRouter, Query, Depends
from sqlalchemy.orm import Session

from app.common.database import messages, users
from app import session, utils

router = APIRouter()

@router.get("/osu-markasread.php")
def mark_channel_as_read(
    database: Session = Depends(session.database.yield_session),
    username: str = Query(..., alias="u"),
    password: str = Query(..., alias="h"),
    channel: str = Query(...)
) -> Response:
    if not (player := users.fetch_by_name(username, session=database)):
        raise HTTPException(401)

    if not utils.check_password(password, player.bcrypt):
        raise HTTPException(401)

    if channel.startswith('#'):
        # We don't support marking public channels as read right now
        return Response(status_code=200)

    safe_name = channel.strip().replace(' ', '_').lower()

    if not (target_user := users.fetch_by_safe_name(safe_name, session=database)):
        raise HTTPException(404)

    messages.update_private_all(
        target_user.id,
        player.id,
        {'read': True},
        session=database
    )
    session.logger.info(
        f"'{player.name}' marked all messages as read in DMs with '{target_user.name}'"
    )
    return Response(status_code=200)
