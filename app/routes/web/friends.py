
from fastapi import APIRouter, HTTPException, Query, Depends
from app.common.database import users, relationships
from sqlalchemy.orm import Session

import utils
import app

router = APIRouter()

@router.get("/osu-getfriends.php")
def get_friends(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias="u"),
    password: str = Query(..., alias="h")
) -> str:
    if not (player := users.fetch_by_name(username, session=session)):
        raise HTTPException(401)

    if not utils.check_password(password, player.bcrypt):
        raise HTTPException(401)

    friends = relationships.fetch_target_ids(
        player.id,
        session=session
    )

    return "\n".join(map(str, friends)).encode()
