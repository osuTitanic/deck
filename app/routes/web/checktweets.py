
from fastapi.responses import PlainTextResponse
from fastapi import APIRouter
import app

router = APIRouter()

@router.get('/osu-checktweets.php')
def bancho_status_message() -> PlainTextResponse:
    """
    This endpoint was used to fetch tweets from @osustatus on twitter/x, which
    would be displayed on the client side. I will be using it here, to display
    a custom message that can be customized later on in the frontend.
    """

    if not (message := app.session.redis.get('bancho:statusmessage')):
        return PlainTextResponse(status_code=200)

    return PlainTextResponse(message)
