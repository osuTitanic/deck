
from typing import Optional, List
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Form
)

from app.constants import CommentTarget, Permissions
from app.common.objects import DBComment

router = APIRouter()

import bcrypt
import app

@router.post('/osu-comment.php')
async def get_comments(
    username: str = Form(..., alias='u'),
    password: str = Form(..., alias='p'),
    playmode: int = Form(..., alias='m'),
    replay_id: int = Form(..., alias='r'),
    beatmap_id: int = Form(..., alias='b'),
    set_id: int = Form(..., alias='s'),
    action: str = Form(..., alias='a'),
    content: Optional[str] = Form(None, alias='comment'),
    time: Optional[int] = Form(None, alias='starttime'),
    color: Optional[str] = Form(None, alias='f'),
    target: Optional[str] = Form(None),
):
    if not (user := app.session.database.user_by_name(username)):
        raise HTTPException(401, detail="Auth")

    if not bcrypt.checkpw(password.encode(), user.bcrypt.encode()):
        raise HTTPException(401, detail="Auth")

    app.session.database.update_latest_activity(user.id)

    if action == 'get':
        comments: List[DBComment] = []
        comments.extend(app.session.database.comments(replay_id, 'replay'))
        comments.extend(app.session.database.comments(beatmap_id, 'map'))
        comments.extend(app.session.database.comments(set_id, 'song'))

        response: List[str] = []

        for comment in comments:
            comment_format = comment.format if comment.format != None else ""
            comment_format = f'{comment_format}{f"|{comment.color}" if comment.color else ""}'

            response.append(
                '\t'.join([
                    str(comment.time),
                    comment.target_type,
                    comment_format,
                    comment.comment
                ])
            )

        return Response('\n'.join(response))

    elif action == 'post':
        try:
            target = CommentTarget(target)
        except ValueError:
            raise HTTPException(400, detail="Invalid target")

        if not (content):
            raise HTTPException(400, detail="No content")

        if len(content) > 80:
            raise HTTPException(400, detail="Content size")

        if not (beatmap := app.session.database.beatmap_by_id(beatmap_id)):
            raise HTTPException(404, detail="Beatmap not found")

        target_id = {
            CommentTarget.Replay: replay_id,
            CommentTarget.Map: beatmap_id,
            CommentTarget.Song: set_id
        }[target]

        permissions = Permissions(user.permissions)

        if Permissions.Subscriber not in permissions:
            color = None

        comment_format = 'player'

        if beatmap.beatmapset.creator == user.name:
            comment_format = 'creator'
        elif Permissions.BAT in permissions:
            comment_format = 'bat'
        elif Permissions.Subscriber in permissions:
            comment_format = 'subscriber'

        app.session.database.submit_comment(
            target_id,
            target.name.lower(),
            user.id,
            time,
            content,
            comment_format,
            beatmap.mode,
            color
        )

        app.session.logger.info(f'<{user.name} ({user.id})> -> Submitted comment on {target.name}: "{content}".')

        return Response('ok')

    raise HTTPException(400, detail="Invalid action")
