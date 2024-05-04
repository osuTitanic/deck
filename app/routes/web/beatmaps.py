
from typing import List, Callable

from fastapi import (
    UploadFile,
    APIRouter,
    Request,
    Depends,
    Query,
    Form,
    File
)

router = APIRouter()

def comma_list(parameter: str) -> Callable:
    async def wrapper(request: Request) -> List[str]:
        query = request.query_params.get(parameter, '')
        return query.split(',')
    return wrapper

def integer_boolean(parameter: str) -> Callable:
    async def wrapper(request: Request) -> bool:
        query = request.query_params.get(parameter, '0')
        return query == '1'
    return wrapper

def integer_boolean_form(parameter: str) -> Callable:
    async def wrapper(request: Request) -> bool:
        form = await request.form()
        query = form.get(parameter, '0')
        return query == '1'
    return wrapper

@router.get('/osu-osz2-bmsubmit-getid.php')
def validate_upload_request(
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    set_id: int = Query(..., alias='s'),
    beatmap_ids: List[str] = Depends(comma_list('b')),
    osz2_hash: str = Query(..., alias='z')
):
    # Validates the upload request and returns
    # the reserved beatmap(set) ids
    ...

@router.post('/osu-osz2-bmsubmit-upload.php')
def upload_beatmap(
    full_submit: bool = Depends(integer_boolean('t')),
    osz2_file: UploadFile = File(..., alias='osz2'),
    osz2_hash: str = Query(..., alias='z'),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    set_id: int = Query(..., alias='s')
):
    # Actually uploads the beatmap
    ...

@router.post('/osu-osz2-bmsubmit-post.php')
def forum_post(
    username: str = Form(..., alias='u'),
    password: str = Form(..., alias='p'),
    set_id: int = Form(..., alias='b'),
    subject: str = Form(...),
    message: str = Form(...),
    complete: bool = Depends(integer_boolean_form('complete')),
    notify: bool = Depends(integer_boolean_form('notify'))
):
    # Creates the forum post and returns its threadId
    ...
