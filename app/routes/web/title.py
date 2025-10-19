
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
) -> Response:
    if redirect:
        # Used when the user clicks on the title image
        return RedirectResponse(config.MENUICON_URL or config.OSU_BASEURL)

    if not config.MENUICON_IMAGE:
        return Response(None)

    if (image := app.session.storage.get_from_cache('assets:title')):
        return Response(image)

    try:
        response = app.session.requests.get(config.MENUICON_IMAGE)
        response.raise_for_status()
    except Exception as e:
        app.session.logger.error(f'Error fetching title image: {e}')
        return Response(None)

    app.session.storage.save_to_cache(
        name='assets:title',
        content=response.content,
        expiry=timedelta(hours=1)
    )

    return Response(response.content)
