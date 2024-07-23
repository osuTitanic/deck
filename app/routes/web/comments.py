
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Request,
    Depends,
    Form
)

from app.common.database.repositories import (
    beatmaps,
    comments,
    groups,
    users
)

from app.common.constants import CommentTarget, Permissions
from app.common.database import DBComment
from app.common.cache import status

router = APIRouter()

import utils
import app

@router.post('/osu-comment.php')
def get_comments(
    request: Request,
    session: Session = Depends(app.session.database.yield_session),
    username: str = Form(..., alias='u'),
    password: str = Form(..., alias='p'),
    action: str = Form(..., alias='a'),
    beatmap_id: int = Form(..., alias='b'),
    replay_id: int = Form(None, alias='r'),
    playmode: int = Form(None, alias='m'),
    set_id: int = Form(None, alias='s'),
    content: Optional[str] = Form(None, alias='comment'),
    time: Optional[int] = Form(None, alias='starttime'),
    color: Optional[str] = Form(None, alias='f'),
    target: Optional[str] = Form(None)
):
    if not (user := users.fetch_by_name(username, session)):
        app.session.logger.warning("Failed to submit comment: Authentication")
        raise HTTPException(401, detail="Auth")

    if not utils.check_password(password, user.bcrypt):
        app.session.logger.warning("Failed to submit comment: Authentication")
        raise HTTPException(401, detail="Auth")

    if not status.exists(user.id):
        app.session.logger.warning("Failed to submit comment: Not logged in")
        raise HTTPException(401, detail='Bancho')

    users.update(user.id, {'latest_activity': datetime.now()}, session)

    if action == 'get':
        db_comments: List[DBComment] = []
        if replay_id: db_comments.extend(comments.fetch_many(replay_id, 'replay', session))
        if beatmap_id: db_comments.extend(comments.fetch_many(beatmap_id, 'map', session))
        if set_id: db_comments.extend(comments.fetch_many(set_id, 'song', session))

        response: List[str] = []

        for comment in db_comments:
            comment_format = comment.format if comment.format != None else ""
            comment_format = f'{comment_format}{f"|{comment.color}" if comment.color else ""}'

            if not set_id or not replay_id:
                # Legacy comments
                response.append(
                    '|'.join([
                        str(comment.time),
                        comment.comment
                    ])
                )
            else:
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
            target = CommentTarget.Map

        if not (content):
            app.session.logger.warning("Failed to submit comment: No content")
            raise HTTPException(400, detail="No content")

        if len(content) > 80:
            app.session.logger.warning("Failed to submit comment: Too large")
            raise HTTPException(400, detail="Content size")

        if not (beatmap := beatmaps.fetch_by_id(beatmap_id, session)):
            app.session.logger.warning("Failed to submit comment: Beatmap not found")
            raise HTTPException(404, detail="Beatmap not found")

        content = content.replace('\t', '') \
                         .replace('|', '')

        target_id = {
            CommentTarget.Replay: replay_id,
            CommentTarget.Map: beatmap_id,
            CommentTarget.Song: set_id
        }[target]

        permissions = Permissions(
            groups.get_player_permissions(user.id, session)
        )

        if Permissions.Supporter not in permissions:
            color = None

        comment_format = 'player'

        if beatmap.beatmapset.creator == user.name:
            comment_format = 'creator'
        elif Permissions.BAT in permissions:
            comment_format = 'bat'
        elif Permissions.Supporter in permissions:
            comment_format = 'subscriber'

        comments.create(
            target_id,
            target.name.lower(),
            user.id,
            time,
            content,
            comment_format,
            beatmap.mode,
            color,
            session
        )

        app.session.logger.info(
            f'<{user.name} ({user.id})> -> Submitted comment on {target.name}: "{content}".'
        )

        utils.track(
            'beatmap_comment',
            user=user,
            request=request,
            properties={
                'target': target.name,
                'id': target_id,
                'content': content
            }
        )

        return Response(f'{time}|{content}\n')

    raise HTTPException(400, detail="Invalid action")
