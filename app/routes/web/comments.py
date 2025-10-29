
from sqlalchemy.orm import Session
from contextlib import suppress
from datetime import datetime
from typing import List
from fastapi import (
    HTTPException,
    APIRouter,
    Depends,
    Form
)

from app.common.constants import CommentTarget, Permissions, UserActivity
from app.common.database import DBComment
from app.common.helpers import activity
from app.common.cache import status
from app.common.database import (
    beatmaps,
    comments,
    groups,
    users
)

router = APIRouter()

import app

@router.post('/osu-comment.php')
def get_comments(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Form(..., alias='u'),
    password: str = Form(..., alias='p'),
    action: str = Form(..., alias='a'),
    beatmap_id: int = Form(..., alias='b'),
    replay_id: int = Form(None, alias='r'),
    playmode: int = Form(None, alias='m'),
    set_id: int = Form(None, alias='s'),
    content: str | None = Form(None, alias='comment'),
    time: int | None = Form(None, alias='starttime'),
    color: str | None = Form(None, alias='f'),
    target: str | None = Form('map')
) -> str:
    if not (user := users.fetch_by_name(username, session)):
        app.session.logger.warning("Failed to submit comment: Authentication")
        raise HTTPException(401, detail="Auth")

    if not app.utils.check_password(password, user.bcrypt):
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

        is_legacy: bool = set_id or not replay_id
        response: List[str] = []

        for comment in db_comments:
            formatted_comment = format_comment(comment, is_legacy)
            response.append(formatted_comment)

        return "\n".join(response)

    elif action == 'post':
        target = CommentTarget.Map

        with suppress(ValueError):
            target = CommentTarget(target)

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

        if not user.is_supporter:
            color = None

        comment_format = 'player'

        if beatmap.beatmapset.creator == user.name:
            comment_format = 'creator'
        elif user.is_bat:
            comment_format = 'bat'
        elif user.is_supporter:
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

        activity.submit(
            user.id, beatmap.mode,
            UserActivity.BeatmapCommented,
            {
                'username': user.name,
                'beatmap_id': beatmap.id,
                'beatmap_name': beatmap.full_name,
                'comment': content
            },
            is_hidden=True,
            session=session
        )

        return f"{time}|{content}\n"

    raise HTTPException(400, detail="Invalid action")

def format_comment(comment: DBComment, legacy: bool = False) -> str:
    comment_format = comment.format if comment.format != None else ""
    comment_format = f'{comment_format}{f"|{comment.color}" if comment.color else ""}'

    if legacy:
        return '|'.join([
            str(comment.time),
            comment.comment
        ])

    return '\t'.join([
        str(comment.time),
        comment.target_type,
        comment_format,
        comment.comment
    ])
