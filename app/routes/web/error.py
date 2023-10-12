
from app.common.database.repositories import logs
from app.common.cache import status

from typing import Optional
from fastapi import (
    HTTPException,
    APIRouter,
    Response,
    Form
)

router = APIRouter()

import json
import app

@router.post('/osu-error.php')
def osu_error(
    username: str = Form(..., alias='u'),
    user_id: Optional[int] = Form(None, alias='i'),
    language: str = Form(..., alias='culture'),
    mode: str = Form(..., alias='gamemode'),
    time: int = Form(..., alias='gametime'),
    beatmap_id: Optional[int] = Form(None, alias='b'),
    beatmap_md5: Optional[str] = Form(None, alias='bc'),
    audiotime: int = Form(...),
    exception: str = Form(...),
    stacktrace: str = Form(...),
    feedback: Optional[str] = Form(None),
    iltrace: Optional[str] = Form(None),
    exehash: Optional[str] = Form(None),
    version: str = Form(...),
    config: str = Form(...)
):
    if not status.exists(user_id):
        raise HTTPException(400)

    app.session.logger.warning('\n'.join([
        f'Client error from "{username}":',
        f'  Version: {version} ({exehash})',
        f'  Mode: {mode}',
        f'  Language: {language}',
        f'  Feedback: {feedback}',
        f'  Iltrace: {iltrace}',
        f'  Exception: {exception}',
        f'  Stacktrace:\n    {stacktrace}'
    ]))

    logs.create(
        json.dumps({
            'user_id': user_id,
            'version': version,
            'feedback': feedback,
            'iltrace': iltrace,
            'exception': exception,
            'stacktrace': stacktrace
        }),
        'error',
        'osu-error'
    )

    app.session.events.submit(
        'bot_message',
        message=f'Client error from "{username}". Plase check the logs!',
        target='#admin'
    )

    return Response('ok')
