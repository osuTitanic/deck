
from fastapi.responses import Response, RedirectResponse
from fastapi import APIRouter, Query
from datetime import timedelta
from typing import Optional

import config
import app

router = APIRouter()

@router.get('/osu-title-image.php')
def legacy_menu_icon(
    image_checksum: Optional[str] = Query('', alias='c'),
    redirect: Optional[bool] = Query(False, alias='l')
):
    if redirect:
        if not config.MENUICON_URL:
            return RedirectResponse(f'http://osu.{config.DOMAIN_NAME}')

        return RedirectResponse(config.MENUICON_URL)

    if not config.MENUICON_IMAGE:
        return Response(None)

    if (image := app.session.storage.get_from_cache('assets:title')):
        return Response(image)

    response = app.session.requests.get(config.MENUICON_IMAGE)

    if not response.ok:
        return Response(None)

    app.session.storage.save_to_cache(
        name='assets:title',
        content=response.content,
        expiry=timedelta(hours=1)
    )

    return Response(response.content)
