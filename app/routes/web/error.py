
from fastapi import APIRouter, Response, Form
from typing import Optional

router = APIRouter()

import app

@router.post('/osu-error.php')
async def osu_error(
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
    version: str = Form(...),
    exehash: str = Form(...),
    config: str = Form(...)
):
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

    # TODO: Better formatting
    # TODO: Submit to database
    # TODO: Exceptions to #admin

    return Response('ok')
