
from sqlalchemy.orm import Session
from datetime import datetime
from typing import List
from osz2 import *

from app.common.config import config_instance as config
from app.helpers.bss import *
from app.helpers.bss_decorators import (
    integer_boolean_form,
    catch_bss_errors,
    integer_boolean,
    query_or_form,
    comma_list,
    file
)

from fastapi import (
    UploadFile,
    APIRouter,
    Response,
    Depends,
    Query,
    Form
)

import hashlib
import math
import app

router = APIRouter()

"""
osz2 beatmap submission endpoints
"""

@router.get('/osu-osz2-bmsubmit-getid.php')
@catch_bss_errors("A server error occurred. Please try again!")
def validate_upload_request(
    session: Session = Depends(app.session.database.yield_session),
    beatmap_ids: List[int] = Depends(comma_list('b', int)),
    osz2_hash: str = Query(..., alias='z'),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    set_id: int = Query(..., alias='s')
) -> Response:
    """
    Prepare a beatmap submission & (re)assign server-side beatmap IDs.
    This is called before uploading the actual osz2 package to let the client know if the submission can proceed.
    """
    if not config.BEATMAP_SUBMISSION_ENABLED:
        app.session.logger.warning('The beatmap submission system is currently disabled. Aborting...')
        return error_response(5, 'The beatmap submission system is currently disabled. Please try again later!')

    error, user = authenticate_user(
        username,
        password,
        session=session
    )

    if error:
        # Failed to authenticate user
        return error

    if not user:
        return error_response(5, 'Authentication failed. Please check your username and password and try again!')

    # Delete any inactive beatmaps
    delete_inactive_beatmaps(user, session=session)

    remaining_beatmaps = remaining_beatmap_uploads(user, session)
    bubbled = False

    if beatmapset := resolve_beatmapset(set_id, beatmap_ids, session):
        # User wants to update an existing beatmapset
        resolved_set_id = beatmapset.id

        allowed_beatmaps, can_update_resources = beatmap_update_permissions(
            user,
            beatmapset,
            session=session
        )

        if not allowed_beatmaps:
            app.session.logger.warning(f'Failed to update beatmapset: User does not own the beatmapset')
            return error_response(1)

        if beatmapset.server != 1:
            app.session.logger.warning(f'Failed to update beatmapset: Beatmapset is not on Titanic')
            return error_response(1)

        if beatmapset.status > 0:
            app.session.logger.warning(f'Failed to update beatmapset: Beatmapset is ranked or loved')
            return error_response(3)

        if beatmapset.status == -2:
            app.session.logger.warning(f'Failed to update beatmapset: Beatmapset is graveyarded')
            return error_response(4)

        if not can_update_resources and len(beatmap_ids) != len(beatmapset.beatmaps):
            app.session.logger.warning(f'Failed to update beatmapset: User is not allowed to add additional beatmaps')
            return error_response(5, 'You are not allowed to add additional beatmaps to this beatmapset.')

        # Create/Remove new beatmaps if necessary
        updated_beatmap_ids = update_beatmaps(
            user,
            beatmap_ids,
            beatmapset,
            session=session
        )

        if updated_beatmap_ids is None:
            return error_response(5, 'Please ask the owner of this beatmapset to delete your beatmap.')

        # Get "bubbled" status
        bubbled = is_bubbled(
            beatmapset,
            session
        )

        app.session.logger.info(f'{user.name} wants to update a beatmapset ({resolved_set_id})')

    else:
        # User wants to upload a new beatmapset
        if remaining_beatmaps <= 0:
            app.session.logger.warning(f'Failed to create beatmapset: User has no remaining beatmap uploads')
            return error_response(5, "You have reached your maximum amount of beatmaps you can upload.")

        # Create a new empty beatmapset inside the database
        resolved_set_id, updated_beatmap_ids = create_beatmapset(
            user,
            beatmap_ids,
            session=session
        )

        if resolved_set_id is None:
            return error_response(5, "An error occurred while creating the beatmapset.")

        app.session.logger.info(f'{user.name} wants to create a new beatmapset ({resolved_set_id})')

    # Either we don't have the osz2 file or the client has no osz2 file
    # If full-submit is true, the client will submit a patch file
    full_submit = is_full_submit(resolved_set_id, osz2_hash)

    return Response('\n'.join([
        '0',
        f'{resolved_set_id}',
        ','.join(map(str, updated_beatmap_ids)),
        f'{int(full_submit)}',
        f'{remaining_beatmaps}',
        f'{int(bubbled)}'
    ]))

@router.post('/osu-osz2-bmsubmit-upload.php')
@catch_bss_errors("Something went wrong while processing your beatmap. Please try again!")
def upload_beatmap(
    session: Session = Depends(app.session.database.yield_session),
    submission_file: UploadFile = Depends(file('0', 'osz2')),
    full_submit: bool = Depends(integer_boolean('t')),
    osz2_hash: str = Depends(query_or_form('z')),
    username: str = Depends(query_or_form('u')),
    password: str = Depends(query_or_form('h')),
    set_id: int = Depends(query_or_form('s'))
):
    """
    Upload and apply an osz2 beatmap submission.
    This is called after the client receives IDs from the submission preparation endpoint.
    The beatmap metadata, .osz package, .osu files, and other resources will be updated on the server.
    """
    if not config.BEATMAP_SUBMISSION_ENABLED:
        app.session.logger.warning('The beatmap submission system is currently disabled. Aborting...')
        return error_response(5, 'The beatmap submission system is currently disabled. Please try again later!')

    error, user = authenticate_user(
        username,
        password,
        session=session
    )

    if error:
        # Failed to authenticate user
        return error

    if not user:
        return error_response(5, 'Authentication failed. Please check your username and password and try again!')

    beatmapset = beatmapsets.fetch_one(set_id, session)

    if not beatmapset:
        app.session.logger.warning(f'Failed to upload beatmap: Beatmapset not found')
        return error_response(5, 'The beatmapset you are trying to upload to does not exist. Please try again!')

    allowed_beatmaps, can_update_resources = beatmap_update_permissions(
        user,
        beatmapset,
        session=session
    )

    if not allowed_beatmaps:
        app.session.logger.warning(f'Failed to upload beatmap: User does not own the beatmapset')
        return error_response(1)

    if beatmapset.server != 1:
        app.session.logger.warning(f'Failed to upload beatmap: Beatmapset is not on Titanic')
        return error_response(1)

    if beatmapset.status > 0:
        app.session.logger.warning(f'Failed to upload beatmap: Beatmapset is ranked or loved')
        return error_response(3)

    if beatmapset.status == -2:
        app.session.logger.warning(f'Failed to upload beatmap: Beatmapset is graveyarded')
        return error_response(4)

    if submission_file.size and submission_file.size > 100_000_000: # 100 MB
        app.session.logger.warning(f'Failed to upload beatmap: osz2 file is too large ({submission_file.size} bytes)')
        return error_response(5, 'Your beatmap is too big. Try to reduce its filesize and try again!')

    osz2_file = submission_file.file.read()

    if len(osz2_file) > 100_000_000: # 100 MB
        app.session.logger.warning(f'Failed to upload beatmap: osz2 file is too large ({len(osz2_file)} bytes)')
        return error_response(5, 'Your beatmap is too big. Try to reduce its filesize and try again!')

    if not full_submit:
        # User uploaded a patch file
        current_osz2_file = app.session.storage.get_osz2(set_id)

        if not current_osz2_file:
            app.session.logger.warning(f'Failed to upload beatmap: Full submit requested but osz2 file is missing')
            return error_response(5, 'The osz2 file is missing. Please try again!')

        # Apply the patch to the current osz2 file
        osz2_file = bss.patch_osz2(
            osz2_file,
            current_osz2_file
        )

    if not osz2_file:
        app.session.storage.remove_osz2(set_id)
        app.session.logger.warning(f'Failed to upload beatmap: Failed to read osz2 file ({full_submit})')
        return error_response(5, 'Something went wrong while processing your beatmap. Please try again!')

    # Verify osz2 hash
    server_hash = hashlib.md5(osz2_file).hexdigest()

    if osz2_hash and osz2_hash != server_hash:
        app.session.storage.remove_osz2(set_id)
        app.session.logger.warning(f'Failed to upload beatmap: osz2 hash mismatch (client: {osz2_hash} / server: {server_hash})')
        return error_response(5, 'Something went wrong while processing your beatmap. Please try again!')

    # Decrypt osz2 file
    osz2 = bss.decrypt_osz2(osz2_file)

    if not osz2:
        app.session.storage.remove_osz2(set_id)
        app.session.logger.error(f'Failed to upload beatmap: Failed to decrypt osz2 file')
        return error_response(5, 'Something went wrong while processing your beatmap. Please try again!')

    if beatmapset.creator_id != user.id:
        # User was invited for a beatmap collaboration
        # We want to make sure they can only update the
        # files that they are allowed to update
        osz2.files = adjust_files_for_collaboration(
            osz2.files,
            existing_files(beatmapset.id),
            allowed_beatmaps,
            can_update_resources
        )

    # Check if the user is trying to upload someone else's beatmap
    if duplicate_beatmap_files(beatmapset, osz2.files, session):
        app.session.logger.warning(f'Failed to upload beatmap: Duplicate beatmap files')
        return error_response(5, 'It seems like one of your beatmaps was already uploaded by someone else. Please try again!')

    allowed_usernames: set[str] = {
        beatmapset.creator_user.name,
        user.name
    }

    # Allow usernames of collaborators
    allowed_usernames.update(
        username
        for beatmap in beatmapset.beatmaps
        for usernames in collaborations.fetch_usernames(beatmap.id, session)
        for username in usernames
    )

    # Allow past usernames
    allowed_usernames.update(
        name_change.name
        for name_change in names.fetch_all_reserved(user.id, session)
    )

    if not validate_beatmap_owner(osz2.metadata, osz2.beatmaps, allowed_usernames) and not user.is_bat:
        app.session.logger.warning(f'Failed to upload beatmap: User does not own the beatmapset')
        return error_response(1)

    max_beatmap_length = bss.maximum_beatmap_length(osz2.beatmaps.values())

    if max_beatmap_length <= 1:
        app.session.logger.warning(f'Failed to upload beatmap: Beatmap length is too short')
        return error_response(5, 'Your beatmap is too short. Please try to make it longer and try again!')

    osz_package = bss.create_osz_package(osz2.files)
    package_filesize = len(osz_package)
    size_limit = bss.calculate_size_limit(max_beatmap_length)

    if package_filesize > size_limit and not user.is_bat:
        app.session.logger.warning(
            f'Failed to upload beatmap: Beatmap package is too large '
            f'({package_filesize} / {size_limit} bytes)'
        )
        return error_response(5, 'Your beatmap is too big. Try to reduce its filesize and try again!')

    previous_status = beatmapset.status

    # Update metadata for beatmapset and beatmaps
    update_beatmap_metadata(
        beatmapset,
        osz2.files,
        osz2.metadata,
        osz2.beatmaps,
        session
    )

    # Create & upload .osz file
    update_beatmap_package(
        beatmapset.id,
        osz2.files,
        osz_package,
        session
    )

    # Update beatmap assets
    update_beatmap_thumbnail(beatmapset, osz2.beatmaps, osz2.files)
    update_beatmap_audio(beatmapset, osz2.beatmaps, osz2.files)
    update_beatmap_files(osz2.files, session=session)

    if config.BEATMAP_SUBMISSION_STORE_OSZ2:
        # Upload the osz2 file to storage
        app.session.storage.upload_osz2(set_id, osz2_file)

    # Update osz2 hashes
    update_osz2_hashes(set_id, osz2, session)

    app.session.logger.info(
        f'{user.name} successfully {"uploaded" if full_submit else "updated"} a beatmapset '
        f'({config.OSU_BASEURL}/s/{set_id})'
    )

    # Depending on if the beatmap is new or updated, different event types should be used
    broadcast_type = broadcast_upload_activity if previous_status == -3 else broadcast_update_activity
    broadcast_type(beatmapset, session)

    return Response('0')

@router.post('/osu-osz2-bmsubmit-post.php')
def forum_post(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Form(..., alias='u'),
    password: str = Form(..., alias='p'),
    set_id: int = Form(..., alias='b'),
    subject: str = Form(...),
    message: str = Form(...),
    complete: bool = Depends(integer_boolean_form('complete')),
    notify: bool = Depends(integer_boolean_form('notify'))
) -> Response:
    """
    Create or update a beatmap's forum topic. This is called after clicking the "Submit" button on the submission form.
    It also updates the beatmapset's description and status based on the "complete" flag (WIP / Pending).
    """
    error, user = authenticate_user(
        username,
        password,
        session=session
    )

    if error or not user:
        # Failed to authenticate user
        return Response(status_code=403)

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
        topic_id = create_beatmap_topic(
            set_id, user.id,
            subject, message,
            not complete, notify,
            session=session
        )
        return Response(f'{topic_id}')

    if not (topic := topics.fetch_one(beatmapset.topic_id, session)):
        topic_id = create_beatmap_topic(
            set_id, user.id,
            subject, message,
            not complete, notify,
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

    return Response(f'{topic.id}')

@router.get('/osu-get-beatmap-topic.php')
def topic_contents(
    session: Session = Depends(app.session.database.yield_session),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    set_id: int = Query(..., alias='s')
):
    """
    Get an existing beatmap's forum topic contents.
    The client will use this to display the beatmap's description, which the user can update accordingly.
    """
    error, _ = authenticate_user(
        username,
        password,
        session=session
    )

    if error:
        # Failed to authenticate user
        return error

    if not (beatmapset := beatmapsets.fetch_one(set_id, session)):
        app.session.logger.warning(f'Failed to fetch beatmapset topic: Beatmapset not found')
        return error_response(1)

    if not beatmapset.topic_id:
        app.session.logger.warning(f'Failed to fetch beatmapset topic: Beatmapset has no topic')
        return error_response(1)

    if not (topic := topics.fetch_one(beatmapset.topic_id, session)):
        app.session.logger.warning(f'Failed to fetch beatmapset topic: Topic not found')
        return error_response(1)

    first_post = posts.fetch_initial_post(topic.id, session)

    return '\u0003'.join([
        f'0',
        f'{topic.id}',
        f'{topic.title}',
        f'{first_post.content if first_post else ""}',
    ])
