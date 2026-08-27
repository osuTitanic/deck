
from sqlalchemy.orm import Session
from datetime import datetime
from slider import Beatmap
from enum import IntEnum
from osz2 import File

from app.helpers import bss
from app.helpers.bss_decorators import integer_boolean_query, integer_boolean_form, catch_bss_errors
from app.common.database.objects import DBUser, DBForumPost
from app.common.database.repositories import (
    beatmapsets,
    beatmaps,
    topics,
    names,
    posts,
)

from fastapi import (
    File as FastAPIFile,
    UploadFile,
    APIRouter,
    Response,
    Depends,
    Query,
    Form
)

import hashlib
import time
import app

router = APIRouter()

"""
pre-osz2 / legacy beatmap submission endpoints
"""

class SendAction(IntEnum):
    Standard = 0
    FirstBeatmap = 1
    LastBeatmap = 2
    SingleBeatmap = 3

    @classmethod
    def values(cls) -> list:
        return list(cls._value2member_map_.keys())

@router.post('/osu-bmsubmit-getid5.php')
@router.post('/osu-bmsubmit-getid4.php')
@router.post('/osu-bmsubmit-getid3.php')
@router.post('/osu-bmsubmit-getid2.php')
@router.post('/osu-bmsubmit-getid.php')
@catch_bss_errors(legacy=True)
def update_beatmap_files_endpoint(
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p'),
    set_id: int = Query(-1, alias='s'),
    action: SendAction = Query(..., alias='r'),
    has_video: bool = Depends(integer_boolean_query('v')),
    has_storyboard: bool = Depends(integer_boolean_query('sb')),
    beatmap_file: UploadFile = FastAPIFile(..., alias='osu'),
    session: Session = Depends(app.session.database.yield_session)
):
    error, user = bss.authenticate_user(
        username,
        password,
        session=session,
        legacy=True
    )

    if error:
        # Failed to authenticate user
        return error

    if not user:
        return "Authentication failed. Please check your username and password and try again!"

    if beatmap_file.size and beatmap_file.size > 15_000_000: # 15 MB
        app.session.logger.warning(f'Failed to upload beatmap: Beatmap file is too large ({beatmap_file.size} bytes)')
        return "Your beatmap is too big. Try to reduce its filesize and try again!"

    beatmap_file_contents = beatmap_file.file.read()
    beatmap_filename = beatmap_file.filename

    if len(beatmap_file_contents) > 15_000_000: # 15 MB
        app.session.logger.warning(f'Failed to upload beatmap: Beatmap file is too large ({len(beatmap_file_contents)} bytes)')
        return "Your beatmap is too big. Try to reduce its filesize and try again!"

    if not beatmap_filename:
        app.session.logger.warning(f'Failed to upload beatmap: Beatmap filename is empty')
        return "Your beatmap filename is empty. Please try again!"

    # Parse beatmap file
    parsed_beatmap = bss.parse_beatmap(beatmap_file_contents)

    if not parsed_beatmap:
        return "Failed to parse beatmap file. Please try again!"

    if action in (SendAction.FirstBeatmap, SendAction.SingleBeatmap):
        # Handle upload ticket registration
        error = handle_initial_upload(
            user, set_id,
            beatmap_filename,
            parsed_beatmap,
            has_video,
            has_storyboard,
            session=session
        )

        if error:
            return error

    upload_request = bss.get_upload_request(user.id)

    if not upload_request:
        app.session.logger.warning(f'Failed to process upload request: Upload request not found')
        return "An error occurred while processing your beatmap. Please try again!"

    # Create a ticket for the given beatmap
    response_data = handle_common_upload(
        upload_request,
        beatmap_file_contents,
        beatmap_filename,
        user, session
    )

    if not response_data:
        return "An error occurred while processing your beatmap. Please try again!"

    if action in (SendAction.LastBeatmap, SendAction.SingleBeatmap):
        # Validate all beatmaps, update metadata,
        # upload new files, ...
        error = handle_upload_finish(
            upload_request,
            user,
            session
        )

        if error:
            return error

    return response_data

@router.post('/osu-bmsubmit-upload.php')
@catch_bss_errors("Something went wrong while processing your beatmap. Please try again!", legacy=True)
def upload_osz(
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p'),
    ticket: str = Query(..., alias='c'),
    osz_filename: str = Query(..., alias='of'),
    osz_ticket: str = Query(..., alias='oc'),
    file: UploadFile = FastAPIFile(..., alias='osu'),
    set_id: int | None = Query(None, alias='s'),
    is_first: bool = Depends(integer_boolean_query('r')),
    session: Session = Depends(app.session.database.yield_session)
):
    error, user = bss.authenticate_user(
        username,
        password,
        session=session,
        legacy=True
    )

    if error:
        # Failed to authenticate user
        return Response(error.body, 403)

    if user is None:
        return Response("", 403)

    if not (upload_request := bss.get_upload_request(user.id)):
        app.session.logger.warning(f'Failed to upload osz file: Upload request not found')
        return bss.bancho_message("An error occurred while processing your beatmap. Please try again!", user)

    # Ensure set_id has a value - some clients don't send it
    set_id = set_id or upload_request.set_id

    if set_id != upload_request.set_id:
        app.session.logger.warning(f'Failed to upload osz file: Invalid set id')
        return bss.bancho_message("An error occurred while processing your beatmap. Please try again!", user)

    if osz_ticket != upload_request.osz_ticket:
        app.session.logger.warning(f'Failed to upload osz file: Invalid ticket')
        return bss.bancho_message("An error occurred while processing your beatmap. Please try again!", user)

    # Check if we received an osz file
    if ticket != upload_request.osz_ticket:
        # We already updated all beatmap files
        # so we can just return here.
        return "ok"

    # Remove ticket, as it's no longer needed
    bss.remove_upload_request(user.id)

    if file.size and file.size > 100_000_000: # 100 MB
        app.session.logger.warning(f'Failed to upload osz file: file is too large ({file.size} bytes)')
        return bss.bancho_message("Your beatmap is too big. Try to reduce its filesize and try again!", user)

    # Read osz file contents
    osz_data = file.file.read()

    if len(osz_data) > 100_000_000: # 100 MB
        app.session.logger.warning(f'Failed to upload osz file: file is too large ({len(osz_data)} bytes)')
        return bss.bancho_message("Your beatmap is too big. Try to reduce its filesize and try again!", user)

    files = bss.osz_to_files(osz_data)

    osz_map_files = [
        file.filename
        for file in files
        if file.is_beatmap
    ]

    # Ensure we got the same amount of beatmaps
    if len(osz_map_files) != len(upload_request.tickets):
        app.session.logger.warning(f'Failed to upload osz file: Invalid amount of beatmaps')
        return bss.bancho_message("An error occurred while processing your beatmap. Please try again!", user)

    # Check if osz beatmap files are present in upload ticket
    # and compare them with the uploaded osz file
    for upload_ticket in upload_request.tickets:
        if upload_ticket.filename not in osz_map_files:
            app.session.logger.warning(f'Failed to upload osz file: Missing beatmap file')
            return bss.bancho_message("An error occurred while processing your beatmap. Please try again!", user)

        server_file = next(
            file for file in files
            if file.filename == upload_ticket.filename
        )

        ticket_hash = hashlib.md5(upload_ticket.file).hexdigest()
        file_hash = hashlib.md5(server_file.content).hexdigest()

        if ticket_hash != file_hash:
            app.session.logger.warning(f'Failed to upload osz file: Beatmap hash mismatch')
            return bss.bancho_message("An error occurred while processing your beatmap. Please try again!", user)

    beatmap_data: dict[str, Beatmap] = {}

    for beatmap_file in files:
        if not beatmap_file.is_beatmap:
            continue

        parsed_beatmap = bss.parse_beatmap(beatmap_file.content)

        if not parsed_beatmap:
            app.session.logger.warning(f'Failed to upload osz file: Failed to parse beatmap file "{beatmap_file.filename}"')
            return bss.bancho_message("An error occurred while processing your beatmap. Please try again!", user)

        beatmap_data[beatmap_file.filename] = parsed_beatmap

    max_beatmap_length = bss.maximum_beatmap_length(beatmap_data.values())

    if max_beatmap_length <= 1:
        app.session.logger.warning(f'Failed to upload beatmap: Beatmap length is too short')
        return bss.bancho_message("Your beatmap is too short. Please try to make it longer and try again!", user)

    osz_package = bss.create_osz_package(files)
    package_filesize = len(osz_package)
    size_limit = bss.calculate_size_limit(max_beatmap_length)

    if package_filesize > size_limit:
        app.session.logger.warning(f'Failed to upload beatmap: Beatmap package is too large')
        return bss.bancho_message("Your beatmap is too big. Try to reduce its filesize and try again!", user)

    beatmapset = beatmapsets.fetch_one(set_id, session)

    if not beatmapset:
        app.session.logger.warning(f'Failed to upload osz file: Beatmapset not found')
        return bss.bancho_message("An error occurred while processing your beatmap. Please try again!", user)
    
    previous_status = beatmapset.status

    if beatmapset.creator_id != user.id:
        app.session.logger.warning(f'Failed to upload osz file: User does not own the beatmapset')
        return bss.bancho_message("The beatmap you're trying to submit isn't owned by you.", user)

    # Update metadata for beatmapset and beatmaps
    bss.update_beatmap_metadata(
        beatmapset, files,
        upload_request.metadata,
        beatmap_data,
        session
    )

    # Create & upload .osz file
    bss.update_beatmap_package(
        set_id,
        files,
        osz_package,
        session
    )

    # Update beatmap assets
    bss.update_beatmap_thumbnail(beatmapset, beatmap_data, files)
    bss.update_beatmap_audio(beatmapset, beatmap_data, files)
    bss.update_beatmap_files(files, session=session)

    app.session.logger.info(
        f'{user.name} uploaded an osz file for beatmapset ({set_id})'
    )

    # Depending on if the beatmap is new or updated, different event types should be used
    broadcast_type = bss.broadcast_upload_activity if previous_status == -3 else bss.broadcast_update_activity
    broadcast_type(beatmapset, session)
    return "ok"

@router.get('/osu-bmsubmit-novideo.php')
def upload_osz_novideo(osz_filename: str = Query(..., alias='file')):
    # This endpoint was used to generate a no-video osz file
    # after the beatmap submission was done. In our case
    # we don't need to do anything here.
    return Response(status_code=200)

@router.post('/osu-bmsubmit-post3.php')
@router.post('/osu-bmsubmit-post2.php')
@router.post('/osu-bmsubmit-post.php')
def legacy_forum_post(
    username: str = Form(..., alias='u'),
    password: str = Form(..., alias='p'),
    set_id: int = Form(..., alias='b'),
    subject: str = Form(...),
    message: str = Form(...),
    notify: bool = Depends(integer_boolean_form('notify')),
    complete: bool = Depends(integer_boolean_form('complete')),
    bumprequest: bool = Depends(integer_boolean_form('bumprequest')),
    session: Session = Depends(app.session.database.yield_session)
) -> Response:
    error, user = bss.authenticate_user(
        username,
        password,
        session=session,
        legacy=True
    )

    if error or not user:
        return Response(status_code=403)

    # Remove upload request
    bss.remove_upload_request(user.id)

    if not (beatmapset := beatmapsets.fetch_one(set_id, session)):
        app.session.logger.warning(f'Failed to post beatmapset topic: Beatmapset not found')
        return Response(status_code=404)

    if beatmapset.creator_id != user.id:
        app.session.logger.warning(f'Failed to post beatmapset topic: User does not own the beatmapset')
        return Response(status_code=403)

    # Update status based on "comlete" flag
    # and the beatmapset description
    beatmapsets.update(
        set_id,
        {
            'status': 0 if complete else -1,
            'last_update': datetime.now(),
            'description': (
                message.split('---------------\n', 1)[-1]
            )
        },
        session=session
    )

    if not beatmapset.topic_id:
        topic_id = bss.create_beatmap_topic(
            set_id, user.id,
            subject, message,
            not complete, bumprequest,
            session=session
        )
        return Response(f'{topic_id}')

    if not (topic := topics.fetch_one(beatmapset.topic_id, session)):
        topic_id = bss.create_beatmap_topic(
            set_id, user.id,
            subject, message,
            not complete, bumprequest,
            session=session
        )
        return Response(f'{topic_id}')

    topics.update(
        topic.id,
        {
            'title': subject,
            'forum_id': (9 if complete else 10),
            'status_text': (
                'Needs modding'
                if not complete else
                'Waiting for BAT approval'
            )
        },
        session=session
    )

    if first_post := posts.fetch_initial_post(topic.id, session):
        posts.update(
            first_post.id,
            {
                'content': message,
                'forum_id': (9 if complete else 10),
                'deleted': False
            },
            session=session
        )

    # Update subscription/notification status
    if notify:
        topics.add_subscriber(
            topic.id,
            user.id,
            session=session
        )

    else:
        topics.delete_subscriber(
            topic.id,
            user.id,
            session=session
        )

    # TODO: Handle "bumprequest"
    return Response(f'{topic.id}')

def create_ticket_hash(
    filename: str,
    user_id: int,
    is_osz: bool = False
) -> str:
    prefix = 'osz' if is_osz else 'osu'
    string = f'{prefix}:{time.time()}:{user_id}:{filename}'
    return hashlib.sha256(string.encode()).hexdigest()

def handle_initial_upload(
    user: DBUser,
    set_id: int,
    beatmap_filename: str,
    parsed_beatmap: Beatmap,
    has_video: bool,
    has_storyboard: bool,
    session: Session
) -> str | None:
    # Delete any inactive beatmaps
    bss.delete_inactive_beatmaps(user, session=session)

    # Ensure that the user has no pending uploads
    bss.remove_upload_request(user.id)

    osz_ticket = create_ticket_hash(
        beatmap_filename,
        user.id,
        is_osz=True
    )

    # Convert slider beatmap metadata to osz2 metadata dict
    metadata = bss.osz2_metadata_from_beatmap(parsed_beatmap)

    # Resolve set id through filename to prevent potential errors
    existing_beatmap = beatmaps.fetch_by_file(
        beatmap_filename,
        session=session
    )

    if existing_beatmap:
        set_id = existing_beatmap.set_id

    request = bss.UploadRequest(
        set_id,
        osz_ticket,
        has_video,
        has_storyboard,
        metadata
    )

    bss.register_upload_request(user.id, request)

def handle_common_upload(
    upload_request: bss.UploadRequest,
    beatmap_data: bytes,
    beatmap_filename: str,
    user: DBUser,
    session: Session
) -> str | None:
    beatmap_ticket = create_ticket_hash(
        beatmap_filename,
        user.id
    )

    upload_ticket = bss.UploadTicket(
        beatmap_filename,
        beatmap_ticket,
        beatmap_data
    )

    upload_request.tickets.append(upload_ticket)

    beatmapset = beatmapsets.fetch_one(upload_request.set_id, session)
    response = ["old"]

    if not beatmapset:
        # User wants to upload a new beatmapset
        response = ["new"]

        # Create a new empty beatmapset inside the database
        set_id, _ = bss.create_beatmapset(
            user, [],
            session=session
        )

        if set_id is None:
            app.session.logger.warning(f'Failed to create beatmapset: set_id is None')
            return "An error occurred while creating the beatmapset."

        upload_request.set_id = set_id

    # Update upload request
    bss.register_upload_request(
        user.id,
        upload_request
    )
    post: DBForumPost | None = None

    if beatmapset and beatmapset.topic_id:
        post = posts.fetch_initial_post(
            beatmapset.topic_id,
            session=session
        )

        if not post:
            response = ["new"]

    # Format response
    response.append(f'{upload_request.set_id}')
    response.append(f'{upload_request.osz_ticket}')
    response.append(f'{upload_ticket.ticket}')
    response.append(f'{upload_request.osz_filename}')

    if beatmapset and response[0] != "new":
        assert post is not None # sanity check for the type checker
        is_approved = beatmapset.status > 0
        response.append(f'{beatmapset.topic_id or -1}')
        response.append(f'{int(is_approved)}')
        response.append(post.topic.title)
        response.append(post.content)

    return '\n'.join(response)

def handle_upload_finish(request: bss.UploadRequest, user: DBUser, session: Session) -> Response | str | None:
    remaining_beatmaps = bss.remaining_beatmap_uploads(user, session)
    beatmapset = beatmapsets.fetch_one(request.set_id, session)

    if not beatmapset:
        app.session.logger.warning(f'Failed to process upload request: Beatmapset not found')
        return "An error occurred while creating the beatmapset. Please try again!"

    if beatmapset.status == -3 and remaining_beatmaps <= 0:
        app.session.logger.warning(f'Failed to create beatmapset: User has no remaining beatmap uploads')
        return "You have reached your maximum amount of beatmaps you can upload."

    if beatmapset.creator_id != user.id:
        app.session.logger.warning(f'Failed to process upload request: User does not own the beatmapset')
        return bss.error_response(1, legacy=True)

    if beatmapset.server != 1:
        app.session.logger.warning(f'Failed to process upload request: Beatmapset is not on Titanic')
        return bss.error_response(1, legacy=True)

    if beatmapset.status > 0:
        app.session.logger.warning(f'Failed to process upload request: Beatmapset is ranked or loved')
        return bss.error_response(3, legacy=True)

    if beatmapset.status == -2:
        app.session.logger.warning(f'Failed to process upload request: Beatmapset is graveyarded')
        return bss.error_response(4, legacy=True)

    # Collect all files of previous osz, excluding .osu files
    file_map = {
        file.filename: file
        for file in bss.existing_files(beatmapset.id)
        if not file.is_beatmap
    }

    # Add updated maps to the files
    for ticket in request.tickets:
        file_map[ticket.filename] = File(
            ticket.filename,
            content=ticket.file,
            size=len(ticket.file),
            offset=0,
            hash=hashlib.md5(ticket.file).digest(),
            date_created=datetime.now(),
            date_modified=datetime.now()
        )

    files = list(file_map.values())
    beatmap_data: dict[str, Beatmap] = {}

    for ticket in request.tickets:
        parsed_beatmap = bss.parse_beatmap(ticket.file)

        if not parsed_beatmap:
            app.session.logger.warning(f'Failed to process upload request: Failed to parse beatmap file "{ticket.filename}"')
            return "An error occurred while processing your beatmap. Please try again!"

        beatmap_data[ticket.filename] = parsed_beatmap

    allowed_usernames = {
        beatmapset.creator_user.name,
        user.name
    }

    # Allow past usernames
    allowed_usernames.update(
        name_change.name
        for name_change in names.fetch_all_reserved(user.id, session)
    )

    if not bss.validate_beatmap_owner(request.metadata, beatmap_data, allowed_usernames) and not user.is_bat:
        app.session.logger.warning(f'Failed to process upload request: User does not own the beatmapset')
        return bss.error_response(1, legacy=True)

    if bss.duplicate_beatmap_files(beatmapset, files, session):
        app.session.logger.warning(f'Failed to process upload request: Duplicate beatmap files')
        return "It seems like one of your beatmaps was already uploaded by someone else. Please try again!"

    max_beatmap_length = bss.maximum_beatmap_length(beatmap_data.values())

    if max_beatmap_length <= 1:
        app.session.logger.warning(f'Failed to upload beatmap: Beatmap length is too short')
        return "Your beatmap is too short. Please try to make it longer and try again!"

    osz_package = bss.create_osz_package(files)
    package_filesize = len(osz_package)
    size_limit = bss.calculate_size_limit(max_beatmap_length)

    if package_filesize > size_limit:
        app.session.logger.warning(
            f'Failed to upload beatmap: Beatmap package is too large '
            f'({package_filesize} / {size_limit} bytes)'
        )
        return "Your beatmap is too big. Try to reduce its filesize and try again!"

    # Determine if the beatmapset has ever gotten a full submission
    has_full_submit = not all(
        file.is_beatmap
        for file in files
    )

    beatmap_ids = [
        beatmaps.fetch_id_by_filename(ticket.filename, session) or -1
        for ticket in request.tickets
    ]

    # Create/Remove new beatmaps if necessary
    beatmap_ids = bss.update_beatmaps(
        user,
        beatmap_ids,
        beatmapset,
        session=session
    )

    if beatmap_ids is None:
        return bss.error_response(5, 'Please ask the owner of this beatmapset to delete your beatmap.')

    # Update relationships
    session.refresh(beatmapset)

    # Update metadata for beatmapset and beatmaps
    bss.update_beatmap_metadata(
        beatmapset,
        files,
        request.metadata,
        beatmap_data,
        session
    )

    # Update .osz file
    bss.update_beatmap_package(
        beatmapset.id,
        files,
        osz_package,
        session
    )

    # Update beatmap files
    bss.update_beatmap_files(
        files,
        session
    )

    # Set the status to "inactive" if the map
    # has not gotten a full submission before
    if not has_full_submit:
        beatmapsets.update(
            beatmapset.id,
            {'status': -3},
            session=session
        )
        beatmaps.update_by_set_id(
            beatmapset.id,
            {'status': -3},
            session=session
        )
        session.refresh(beatmapset)

    app.session.logger.info(
        f'{user.name} {"created" if beatmapset.status == -3 else "updated"} a beatmapset '
        f'({request.set_id})'
    )
