
from fastapi import APIRouter, Response

import app

router = APIRouter()

@router.get('/osu-checktweets.php')
def bancho_down_message():
    """
    This endpoint was used to fetch tweets from @osustatus on twitter/x, which
    would be displayed on the client side. I will be using it here, to display
    a custom message that can be customized later on in the frontend.
    """

    if (message := app.session.redis.get('bancho:downmessage')):
        return Response(message)

    return Response(
        'Bancho seems to have crashed. '
        'Please contact an administrator, if this issue persists!'
    )
