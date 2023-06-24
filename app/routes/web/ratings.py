
from fastapi.responses import RedirectResponse
from fastapi import APIRouter, Response, Query
from typing import Optional

router = APIRouter()

import bcrypt
import app

@router.get('/osu-rate.php')
def ratings(
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p'),
    beatmap_md5: str = Query(..., alias='c'),
    rating: Optional[int] = Query(None, alias='v')
):
    if not (user := app.session.database.user_by_name(username)):
        return Response('auth fail')
    
    if not bcrypt.checkpw(password.encode(), user.bcrypt.encode()):
        return Response('auth fail')
    
    if not (beatmap := app.session.database.beatmap_by_checksum(beatmap_md5)):
        return Response('no exist')

    if beatmap.status <= 0:
        return Response('not ranked')

    if beatmap.beatmapset.creator == user.name:
        # TODO: This is pretty useless...
        return Response('owner')

    previous_rating = app.session.database.rating(beatmap.md5, user.id)
        
    if previous_rating:
        ratings = app.session.database.ratings(beatmap.md5)

        return Response(
            '\n'.join([
                'alreadyvoted',
                str(sum(ratings) / len(ratings))
            ]))
    
    if rating is None:
        return Response('ok')

    if rating < 0 or rating > 10:
        return RedirectResponse('https://pbs.twimg.com/media/Dqnn54dVYAAVuki.jpg')

    app.session.database.submit_rating(
        user.id,
        beatmap.md5,
        beatmap.set_id,
        rating
    )

    app.session.logger.info(f'<{user.name} ({user.id})> -> Submitted rating of {rating} on "{beatmap.full_name}".')

    ratings = app.session.database.ratings(beatmap.md5)

    return Response(
        '\n'.join([
            'ok',
            str(sum(ratings) / len(ratings))
        ]))
