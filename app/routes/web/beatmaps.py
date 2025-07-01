
from typing import List, Callable, Tuple, Dict, Any
from sqlalchemy.orm import Session
from collections import Counter
from datetime import datetime
from zipfile import ZipFile

from app.common.constants import SendAction, BeatmapGenre, BeatmapLanguage, UserActivity
from app.common.database.objects import DBUser, DBBeatmapset, DBBeatmap
from app.common.helpers import beatmaps as beatmap_helper
from app.common.webhooks import Embed, Image, Author
from app.common.helpers import performance, activity
from app.common.streams import StreamIn
from app.common.cache import status
from app.common import officer

from app.common.database import (
    nominations,
    beatmapsets,
    favourites,
    beatmaps,
    modding,
    ratings,
    topics,
    groups,
    users,
    posts,
    plays
)

from fastapi import (
    HTTPException,
    UploadFile,
    APIRouter,
    Response,
    Request,
    Depends,
    Query,
    Form,
    File
)

import zipfile
import hashlib
import base64
import config
import time
import app
import io

router = APIRouter()

def error_response(
    error_code: int,
    message: str = "",
    legacy: bool = False
) -> Response:
    if not legacy:
        return Response(f'{error_code}\n{message}')

    message_dict = {
        1: "The beatmap you're trying to submit isn't owned by you.",
        2: "The beatmap you're trying to submit is no longer available.",
        3: "The beatmap is already ranked. You cannot update ranked maps.",
        4: "The beatmap is currently in the beatmap graveyard. You can ungraveyard your map by visiting the beatmaps section of your user profile.",
        5: "An error occurred while processing your beatmap."
    }

    fallback_message = message_dict.get(
        error_code,
        'An unknown error occurred.'
    )

    return Response(message or fallback_message)

def authenticate_user(
    username: str,
    password: str,
    session: Session,
    legacy: bool = False
) -> Tuple[Response, DBUser]:
    player = users.fetch_by_name(username, session=session)

    if not player:
        app.session.logger.warning(f'Failed to authenticate user: User not found')
        return error_response(5, 'Authentication failed. Please check your login credentials.', legacy), None

    if not app.utils.check_password(password, player.bcrypt):
        app.session.logger.warning(f'Failed to authenticate user: Invalid password')
        return error_response(5, 'Authentication failed. Please check your login credentials.', legacy), None

    if player.silence_end and player.silence_end > datetime.now():
        app.session.logger.warning(f'Failed to authenticate user: User is silenced')
        return error_response(5, 'You are not allowed to upload beatmaps while silenced.', legacy), None

    if player.restricted:
        app.session.logger.warning(f'Failed to authenticate user: User is restricted')
        return error_response(5, 'You are banned. Please contact support if you believe this is a mistake.', legacy), None

    if not status.exists(player.id):
        app.session.logger.warning(f'Failed to authenticate user: User is not connected to bancho')
        return error_response(5, 'You are not connected to bancho, please try again!', legacy), None

    return None, player

def bancho_message(message: str, user: DBUser) -> Response:
    app.session.events.submit(
        'user_announcement',
        user_id=user.id,
        message=message,
    )
    return Response(message, 400)

def is_bubbled(beatmapset: DBBeatmapset, session: Session) -> bool:
    """Check if a beatmap has the 'bubble' icon on the forums"""
    topic = topics.fetch_one(
        beatmapset.topic_id,
        session=session
    )

    return (
        topic.icon_id == 3
        if topic else False
    )

def pop_bubble(beatmapset: DBBeatmapset, session: Session) -> None:
    """Change the forum icon of the beatmap and increase its star priority by 5"""
    topic = topics.fetch_one(
        beatmapset.topic_id,
        session=session
    )

    if topic:
        # Set icon to "bubblepop"
        topics.update(
            topic.id,
            {'icon_id': 4}, # TODO: Make an enum for this
            session=session
        )

    beatmapsets.update(
        beatmapset.id,
        {'star_priority': DBBeatmapset.star_priority + 5},
        session=session
    )

    nominations.delete_all(
        beatmapset.id,
        session=session
    )

    app.session.logger.debug('Beatmap bubble was popped')

def is_full_submit(set_id: int, osz2_hash: str) -> bool:
    """Determine if the client should upload the full osz2 or a patch file"""
    if not osz2_hash:
        # Client has no osz2 it can patch
        return True

    osz2_file = app.session.storage.get_osz2_internal(set_id)

    if not osz2_file:
        # We don't have an osz2 we can patch
        return True

    # Check if osz2 file is outdated
    return osz2_hash != hashlib.md5(osz2_file).hexdigest()

def delete_inactive_beatmaps(user: DBUser, session: Session = ...) -> None:
    """Delete any beatmaps with the '-3' status, that got never updated"""
    try:
        inactive_sets = beatmapsets.fetch_inactive(
            user.id,
            session=session
        )

        app.session.logger.debug(
            f'Found {len(inactive_sets)} inactive beatmapsets'
        )

        # Remove assets from storage
        for set in inactive_sets:
            app.session.storage.remove_osz2(set.id)
            app.session.storage.remove_osz(set.id)
            app.session.storage.remove_background(set.id)
            app.session.storage.remove_mp3(set.id)

            for beatmap in set.beatmaps:
                app.session.storage.remove_beatmap_file(beatmap.id)

        for set in inactive_sets:
            # Delete all related data
            modding.delete_by_set_id(set.id, session=session)
            ratings.delete_by_set_id(set.id, session=session)
            plays.delete_by_set_id(set.id, session=session)
            nominations.delete_all(set.id, session=session)
            favourites.delete_all(set.id, session=session)
            beatmaps.delete_by_set_id(set.id, session=session)

        # Delete beatmapsets
        beatmapsets.delete_inactive(
            user.id,
            session=session
        )

        # Hide beatmap topic
        for set in inactive_sets:
            topics.update(
                set.topic_id,
                {
                    'status_text': 'Deleted',
                    'hidden': True,
                    'locked_at': datetime.now()
                },
                session=session
            )
    except Exception as e:
        officer.call(
            'Failed to delete inactive beatmaps.',
            exc_info=e
        )

def remaining_beatmap_uploads(user: DBUser, session: Session) -> int:
    user_groups = groups.fetch_user_groups(
        user.id,
        include_hidden=True,
        session=session
    )

    group_names = [group.name for group in user_groups]

    if 'Admins' in group_names:
        # Admins have unlimited uploads
        return 10

    unranked_beatmaps = beatmapsets.fetch_unranked_count(
        user.id,
        session=session
    )

    ranked_beatmaps = beatmapsets.fetch_ranked_count(
        user.id,
        session=session
    )

    if 'Supporter' in group_names:
        # Supporters can upload up to 8 pending maps plus
        # 1 per ranked map, up to a maximum of 12
        return (8 - unranked_beatmaps) + min(ranked_beatmaps, 12)

    # Regular users can upload up to 4 pending maps plus
    # 1 per ranked map, up to a maximum of 8
    return (4 - unranked_beatmaps) + min(ranked_beatmaps, 4)

def create_beatmapset(
    user: DBUser,
    beatmap_ids: List[int],
    session: Session
) -> Tuple[int | None, List[int]]:
    # Create new beatmapset
    set = beatmapsets.create(
        id=beatmap_helper.next_beatmapset_id(session=session),
        creator=user.name,
        creator_id=user.id,
        server=1
    )

    # Create beatmaps
    new_beatmaps = [
        beatmaps.create(
            id=beatmap_helper.next_beatmap_id(session=session),
            set_id=set.id,
            session=session
        )
        for _ in beatmap_ids
    ]

    app.session.logger.info(
        f'Created new beatmapset ({set.id}) for user {user.name}'
    )

    return set.id, [beatmap.id for beatmap in new_beatmaps]

def update_beatmaps(
    beatmap_ids: List[int],
    beatmapset: DBBeatmapset,
    session: Session
) -> List[int]:
    """Create/Delete beatmaps based on the amount of beatmaps the client requested"""
    # Get current beatmaps
    current_beatmap_ids = [
        beatmap.id
        for beatmap in beatmapset.beatmaps
    ]

    if len(beatmap_ids) < len(current_beatmap_ids):
        # Check if beatmap ids are valid & part of the set
        for beatmap_id in beatmap_ids:
            assert beatmap_id in current_beatmap_ids

        # Remove beatmaps
        deleted_maps = [
            beatmap_id
            for beatmap_id in current_beatmap_ids
            if beatmap_id not in beatmap_ids
        ]

        for beatmap_id in deleted_maps:
            plays.delete_by_beatmap_id(beatmap_id, session=session)
            beatmaps.delete_by_id(beatmap_id, session=session)

        app.session.logger.debug(f'Deleted {len(deleted_maps)} beatmaps')
        return beatmap_ids

    # Calculate how many new beatmaps we need to create
    required_maps = max(
        len(beatmap_ids) - len(current_beatmap_ids), 0
    )

    # Create new beatmaps
    new_beatmap_ids = [
        beatmaps.create(
            id=beatmap_helper.next_beatmap_id(session=session),
            set_id=beatmapset.id,
            session=session
        ).id
        for _ in range(required_maps)
    ]

    app.session.logger.debug(f'Created {required_maps} new beatmaps')

    # Return new beatmap ids to the client
    return current_beatmap_ids + new_beatmap_ids

def update_osz2_hashes(set_id: int, osz2_file: bytes, session: Session) -> None:
    stream = StreamIn(osz2_file)
    magic = stream.read(3)
    version = stream.read(1)
    iv = stream.read(16)

    meta_hash = stream.read(16).hex()
    info_hash = stream.read(16).hex()
    body_hash = stream.read(16).hex()

    beatmapsets.update(
        set_id,
        {
            'meta_hash': meta_hash,
            'info_hash': info_hash,
            'body_hash': body_hash
        },
        session=session
    )

def empty_zip_file() -> bytes:
    return b'PK\x05\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'

def update_beatmap_package(
    set_id: int,
    files: Dict[str, bytes],
    session: Session
) -> None:
    app.session.logger.debug(f'Updating beatmap package...')

    allowed_file_extensions = [
        ".osu", ".osz", ".osb", ".osk", ".png", ".mp3", ".jpeg",
        ".wav", ".png", ".wav", ".ogg", ".jpg", ".wmv", ".flv",
        ".mp3", ".flac", ".mp4", ".avi", ".ini", ".jpg", ".m4v"
    ]

    buffer = io.BytesIO()
    zip = ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED)

    for filename, data in files.items():
        if not any(filename.endswith(ext) for ext in allowed_file_extensions):
            continue

        zip.writestr(filename, data)

    zip.close()
    buffer.seek(0)

    app.session.storage.upload_osz(
        set_id,
        buffer.getvalue()
    )

    # Get total length of all video files
    video_file_extensions = [
        ".wmv", ".flv", ".mp4",
        ".avi", ".m4v", ".mpg"
    ]

    video_files = [
        filename
        for filename in files.keys()
        if any(ext in filename for ext in video_file_extensions)
    ]

    total_video_length = sum(
        len(files[filename])
        for filename in video_files
    )

    osz_size = len(buffer.getvalue())
    osz_size_novideo = osz_size - total_video_length

    # Update osz file sizes for osu!direct
    beatmapsets.update(
        set_id,
        {
            'osz_filesize': osz_size,
            'osz_filesize_novideo': osz_size_novideo
        },
        session=session
    )

def calculate_package_size(files: Dict[str, bytes]) -> int:
    buffer = io.BytesIO()
    osz = ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED)

    for filename, data in files.items():
        osz.writestr(filename, data)

    osz.close()
    size = len(buffer.getvalue())

    del buffer
    del osz
    return size

def calculate_size_limit(beatmap_length: int) -> int:
    # The file size limit is 10MB plus an additional 10MB for
    # every minute of beatmap length, and it caps at 100MB.
    return min(
        10_000_000 + (10_000_000 * (beatmap_length / 60)),
        100_000_000
    )

def resolve_beatmapset(
    set_id: int,
    beatmap_ids: List[int],
    session: Session
) -> DBBeatmapset | None:
    if set_id >= 0:
        # Best-case scenario: The client already knows the setId
        return beatmapsets.fetch_one(set_id, session)

    # There are 2 possible scenarios now:
    # 1. The user wants to upload a new beatmapset
    # 2. The user wants to update an existing beatmapset, but doesn't know the setId

    # Query existing beatmap_ids that are valid
    valid_beatmaps = [
        beatmaps.fetch_by_id(beatmap_id, session)
        for beatmap_id in beatmap_ids
        if beatmap_id >= 0
    ]

    # Remove "None" values
    valid_beatmaps = [
        beatmap for beatmap in valid_beatmaps
        if beatmap is not None
    ]

    if not valid_beatmaps:
        return None

    # Check if all beatmaps are part of the same set
    set_ids = {
        beatmap.set_id
        for beatmap in valid_beatmaps
    }

    if len(set_ids) != 1:
        return None

    return valid_beatmaps[0].beatmapset

def resolve_beatmap_id(
    beatmap_ids: List[int],
    beatmap_data: dict,
    filename: str,
    session: Session
) -> int:
    beatmap = beatmap_data[filename]

    # Newer .osu version have the beatmap id in the metadata
    if (beatmap_id := beatmap.get('onlineID', -1)) != -1:
        if beatmap_id in beatmap_ids:
            return beatmap_id

    # Try to get the beatmap id from the filename
    if beatmap := beatmaps.fetch_by_file(filename, session):
        if beatmap.id in beatmap_ids:
            beatmap_ids.remove(beatmap.id)
        return beatmap.id

    return beatmap_ids.pop(0)

def validate_beatmap_owner(
    beatmap_data: dict,
    metadata: dict,
    user: DBUser,
) -> bool:
    if user.is_bat:
        # Allow BAT members to upload any beatmap
        return True

    if metadata.get('Creator') != user.name:
        return False

    for beatmap in beatmap_data.values():
        if beatmap['metadata']['author']['username'] != user.name:
            return False

    return True

def update_beatmap_metadata(
    beatmapset: DBBeatmapset,
    files: dict,
    metadata: dict,
    beatmap_data: dict,
    session: Session
) -> None:
    app.session.logger.debug(f'Updating beatmap metadata...')

    file_extensions = [
        filename.split('.')[-1]
        for filename in files.keys()
    ]

    video_file_extensions = [
        "wmv", "flv", "mp4",
        "avi", "m4v", "mpg"
    ]

    # Map is in "wip", until the user posts it to the forums
    status = (-1 if beatmapset.status <= -1 else 0)

    # Try to detect genre & language from tags
    tags = metadata.get('Tags', '').split()
    detected_language = detect_language_from_tags(tags)
    detected_genre = detect_genre_from_tags(tags)

    # Update beatmapset metadata
    beatmapsets.update(
        beatmapset.id,
        {
            'artist': metadata.get('Artist'),
            'title': metadata.get('Title'),
            'creator': metadata.get('Creator'),
            'source': metadata.get('Source'),
            'tags': metadata.get('Tags'),
            'artist_unicode': metadata.get('ArtistUnicode'),
            'title_unicode': metadata.get('TitleUnicode'),
            'source_unicode': metadata.get('SourceUnicode'),
            'has_video': any(ext in file_extensions for ext in video_file_extensions),
            'language_id': (
                detected_language.value
                if beatmapset.language_id <= 1
                else beatmapset.language_id
            ),
            'genre_id': (
                detected_genre.value
                if beatmapset.genre_id <= 1
                else beatmapset.genre_id
            ),
            'display_title': (
                f'[bold:0,size:20]{metadata.get("Artist", "")}|'
                f'[]{metadata.get("Title", "")}'
            ),
            'has_storyboard': (
                'osb' in file_extensions or
                'osq' in file_extensions
            ),
            'last_update': datetime.now(),
            'status': status
        },
        session=session
    )

    beatmap_ids = sorted([
        beatmap.id
        for beatmap in beatmapset.beatmaps
    ])

    assert len(beatmap_ids) == len(beatmap_data)

    for filename, beatmap in beatmap_data.items():
        difficulty_attributes = performance.calculate_difficulty(
            files[filename],
            beatmap['ruleset']['onlineID']
        )

        beatmap_id = resolve_beatmap_id(
            beatmap_ids,
            beatmap_data,
            filename,
            session=session
        )

        assert difficulty_attributes is not None
        assert beatmap_id is not None

        beatmaps.update(
            beatmap_id,
            {
                'status': status,
                'filename': filename,
                'last_update': datetime.now(),
                'drain_length': round(beatmap['drainLength'] / 1000),
                'total_length': round(beatmap['totalLength'] / 1000),
                'md5': hashlib.md5(files[filename]).hexdigest(),
                'version': beatmap['difficultyName'] or 'Normal',
                'mode': beatmap['ruleset']['onlineID'],
                'bpm': beatmap['bpm'],
                'hp': beatmap['difficulty']['drainRate'],
                'cs': beatmap['difficulty']['circleSize'],
                'od': beatmap['difficulty']['overallDifficulty'],
                'ar': beatmap['difficulty']['approachRate'],
                'count_normal': difficulty_attributes.n_circles or 0,
                'count_slider': difficulty_attributes.n_sliders or 0,
                'count_spinner': difficulty_attributes.n_spinners or 0,
                'max_combo': difficulty_attributes.max_combo,
                'diff': difficulty_attributes.stars
            },
            session=session
        )

    # Refresh beatmapset object & check for
    # remaining inactive beatmaps
    session.refresh(beatmapset)

    for beatmap in beatmapset.beatmaps:
        if beatmap.status != -3:
            continue

        # Remove inactive beatmap
        plays.delete_by_beatmap_id(beatmap.id, session=session)
        beatmaps.delete_by_id(beatmap.id, session=session)

    if is_bubbled(beatmapset, session):
        # Bubble should be popped when the beatmap
        # gets updated. It will re-gain 5 star priority
        pop_bubble(beatmapset, session)

def update_beatmap_thumbnail(set_id: int, files: dict, beatmaps: dict) -> None:
    app.session.logger.debug(f'Uploading beatmap thumbnail...')

    # Delete cached thumbnails
    app.session.redis.delete(f'mt:{set_id}', f'mt:{set_id}l')

    background_files = [
        beatmap['metadata']['backgroundFile']
        for beatmap in beatmaps.values()
        if beatmap['metadata']['backgroundFile']
    ]

    if not background_files:
        app.session.logger.debug(f'Background file not specified. Skipping...')
        return

    target_background = background_files[0]

    if target_background not in files:
        app.session.logger.debug(f'Background file not found. Skipping...')
        return

    thumbnail = app.utils.resize_and_crop_image(
        files[target_background],
        target_width=160,
        target_height=120
    )

    app.session.storage.upload_background(
        set_id,
        thumbnail
    )

def update_beatmap_audio(set_id: int, files: dict, beatmaps: dict) -> None:
    app.session.logger.debug(f'Uploading beatmap audio preview...')

    # Delete cached preview
    app.session.redis.delete(f'mp3:{set_id}')

    beatmaps_with_audio = [
        beatmap
        for beatmap in beatmaps.values()
        if beatmap['metadata']['audioFile']
    ]

    if not beatmaps_with_audio:
        app.session.logger.debug(f'Audio file not specified. Skipping...')
        return

    target_beatmap = beatmaps_with_audio[0]
    audio_file = target_beatmap['metadata']['audioFile']
    audio_offset = target_beatmap['metadata']['previewTime']

    if audio_file not in files:
        app.session.logger.debug(f'Audio file not found. Skipping...')
        return

    audio_snippet = app.utils.extract_audio_snippet(
        files[audio_file],
        offset_ms=audio_offset
    )

    app.session.storage.upload_mp3(
        set_id,
        audio_snippet
    )

def update_beatmap_files(files: dict, session: Session) -> None:
    app.session.logger.debug(f'Uploading beatmap files...')

    for filename, content in files.items():
        if not filename.endswith('.osu'):
            continue

        beatmap_id = beatmaps.fetch_id_by_filename(filename, session)
        assert beatmap_id is not None

        app.session.storage.upload_beatmap_file(
            beatmap_id,
            content
        )

LanguageDict = {
    BeatmapLanguage(language_id).name.lower(): BeatmapLanguage(language_id)
    for language_id in BeatmapLanguage.values()
}

GenreDict = {
    BeatmapGenre(genre_id).name.lower(): BeatmapGenre(genre_id)
    for genre_id in BeatmapGenre.values()
}

def detect_language_from_tags(tags: List[str]) -> BeatmapLanguage:
    for tag in tags:
        filtered_tag = tag.lower().strip(",").strip()

        if language := LanguageDict.get(filtered_tag):
            return language

    return BeatmapLanguage.Unspecified

def detect_genre_from_tags(tags: List[str]) -> BeatmapGenre:
    for tag in tags:
        filtered_tag = tag.lower().strip(",").strip()

        if genre := GenreDict.get(filtered_tag):
            return genre

    return BeatmapGenre.Unspecified

def duplicate_beatmap_files(files: dict, creator_id: int, session: Session) -> bool:
    """Check for duplicate beatmap filenames & checksums"""
    for filename, content in files.items():
        if not filename.endswith('.osu'):
            continue

        if beatmap := beatmaps.fetch_by_file(filename, session):
            if beatmap.beatmapset.creator_id != creator_id:
                return True

        beatmap_hash = hashlib.md5(content).hexdigest()

        if beatmap := beatmaps.fetch_by_checksum(beatmap_hash, session):
            if beatmap.beatmapset.creator_id != creator_id:
                return True

    return False

def default_topic_message(set_id: int, session: Session) -> str:
    beatmapset = beatmapsets.fetch_one(
        set_id,
        session=session
    )

    if not beatmapset:
        return ''

    submission_time = datetime.now().strftime('%A, %d. %B %Y %I:%M%p')

    max_beatmap_length = max(
        beatmap.total_length
        for beatmap in beatmapset.beatmaps
    )

    max_beatmap_bpm = max(
        beatmap.bpm
        for beatmap in beatmapset.beatmaps
    )

    play_time_minutes = max_beatmap_length // 60
    play_time_seconds = max_beatmap_length % 60

    return '\n'.join([
        f'[size=85]This beatmap was submitted using in-game submission on {submission_time}[/size]',
        '',
        f'[b]Artist:[/b] {beatmapset.artist}',
        f'[b]Title:[/b] {beatmapset.title}',
        f'[b]Source:[/b] {beatmapset.source}',
        f'[b]Tags:[/b] {beatmapset.tags}',
        f'[b]BPM:[/b] {max_beatmap_bpm}',
        f'[b]Filesize:[/b] {round(beatmapset.osz_filesize / 1000)}kb',
        f'[b]Play Time:[/b] {play_time_minutes}:{play_time_seconds}',
        f'[b]Difficulties Available:[/b]',
        '[list]',
        *(
            f'[*][url=http://osu.{config.DOMAIN_NAME}/api/beatmaps/osu/{beatmap.id}]{beatmap.version}[/url] ({round(beatmap.diff, 2)} stars)'
            for beatmap in beatmapset.beatmaps
        ),
        '[/list]',
        '',
        f'[size=150][b]Download: [url=http://osu.{config.DOMAIN_NAME}/d/{beatmapset.id}]{beatmapset.artist} - {beatmapset.title}[/url][/b][/size]',
        f'[b]Information:[/b] [url=http://osu.{config.DOMAIN_NAME}/s/{beatmapset.id}]Scores/Beatmap Listing[/url]',
        '---------------',
        'Use this space to tell the world about your map. It helps to include a list of changes as your map is modded!'
    ])

def create_beatmap_topic(
    set_id: int,
    user_id: int,
    subject: str,
    message: str,
    wip: bool,
    notify: bool,
    session: Session
) -> int:
    app.session.logger.debug(f'Creating beatmap topic...')

    if '---------------' not in message.splitlines():
        message = default_topic_message(
            set_id,
            session=session
        )

    topic = topics.create(
        forum_id=(10 if wip else 9),
        title=subject,
        creator_id=user_id,
        can_change_icon=False,
        status_text=(
            'Needs modding'
            if wip else
            'Waiting for BAT approval'
        )
    )

    posts.create(
        topic.id,
        topic.forum_id,
        topic.creator_id,
        message,
        edit_locked=True,
        session=session
    )

    beatmapsets.update(
        set_id,
        {'topic_id': topic.id},
        session=session
    )

    # Update subscription/notification status
    if notify:
        topics.add_subscriber(
            topic.id,
            user_id,
            session=session
        )

    app.session.logger.info(f'Created beatmap topic for beatmapset ({topic.id})')
    return topic.id

def broadcast_upload_activity(beatmapset: DBBeatmapset, session: Session) -> None:
    # Post to userpage & #announce channel
    activity.submit(
        beatmapset.creator_id,
        resolve_primary_mode(beatmapset.beatmaps),
        UserActivity.BeatmapUploaded,
        {
            'title': beatmapset.title,
            'artist': beatmapset.artist,
            'username': beatmapset.creator,
            'beatmapset_id': beatmapset.id,
            'beatmapset_name': beatmapset.full_name,
        },
        is_announcement=True,
        session=session
    )

def broadcast_update_activity(beatmapset: DBBeatmapset, session: Session) -> None:
    last_activity = activity.activities.fetch_last(
        beatmapset.creator_id,
        session
    )

    is_duplicate = (
        last_activity is not None and
        last_activity.type in (UserActivity.BeatmapUploaded, UserActivity.BeatmapUpdated) and
        last_activity.data['beatmapset_id'] == beatmapset.id
    )

    # Post to userpage
    activity.submit(
        beatmapset.creator_id,
        resolve_primary_mode(beatmapset.beatmaps),
        UserActivity.BeatmapUpdated,
        {
            'username': beatmapset.creator,
            'beatmapset_id': beatmapset.id,
            'beatmapset_name': beatmapset.full_name
        },
        is_hidden=is_duplicate,
        session=session
    )

def resolve_primary_mode(beatmaps: List[DBBeatmap]) -> int:
    counter = Counter([beatmap.mode for beatmap in beatmaps])
    return counter.most_common(1)[0][0] if counter else 0

def comma_list(parameter: str, cast=str) -> Callable:
    async def wrapper(request: Request) -> List[Any]:
        try:
            query = request.query_params.get(parameter, '')
            return [cast(value) for value in query.split(',')]
        except ValueError:
            raise HTTPException(400, 'Invalid query parameter')
    return wrapper

def integer_boolean_query(parameter: str) -> Callable:
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

def integer_boolean(parameter: str) -> Callable:
    async def wrapper(request: Request) -> bool:
        query = request.query_params.get(parameter)

        if query is not None:
            return query == '1'

        # Try to use form data as a backup
        form = await request.form()
        query = form.get(parameter)
        return query == '1'
    return wrapper

def query_or_form(alias: str) -> Callable:
    async def wrapper(request: Request) -> str:
        query = request.query_params.get(alias)

        if query is not None:
            return query

        form = await request.form()

        if alias not in form:
            raise HTTPException(
                status_code=400,
                detail=f'Missing required parameter: {alias}'
            )

        return form[alias]
    return wrapper

def file(*aliases) -> Callable:
    async def wrapper(request: Request) -> UploadFile:
        form = await request.form()

        for alias in aliases:
            if alias in form:
                return form[alias]

        raise HTTPException(
            status_code=400,
            detail=f'Missing required file parameter: {", ".join(aliases)}'
        )
    return wrapper

@router.get('/osu-osz2-bmsubmit-getid.php')
def validate_upload_request(
    session: Session = Depends(app.session.database.yield_session),
    beatmap_ids: List[int] = Depends(comma_list('b', int)),
    osz2_hash: str = Query(..., alias='z'),
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='h'),
    set_id: int = Query(..., alias='s')
) -> Response:
    if not config.OSZ2_SERVICE_URL:
        app.session.logger.warning('The osz2-service url was not found. Aborting...')
        return error_response(5, 'The beatmap submission system is currently disabled. Please try again later!')

    error, user = authenticate_user(
        username,
        password,
        session=session
    )

    if error:
        # Failed to authenticate user
        return error

    # Delete any inactive beatmaps
    delete_inactive_beatmaps(user, session=session)

    remaining_beatmaps = remaining_beatmap_uploads(user, session)
    bubbled = False

    if beatmapset := resolve_beatmapset(set_id, beatmap_ids, session):
        # User wants to update an existing beatmapset
        set_id = beatmapset.id

        if beatmapset.creator_id != user.id:
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

        # Create/Remove new beatmaps if necessary
        beatmap_ids = update_beatmaps(
            beatmap_ids,
            beatmapset,
            session=session
        )

        # Get "bubbled" status
        bubbled = is_bubbled(
            beatmapset,
            session
        )

        app.session.logger.info(f'{user.name} wants to update a beatmapset ({set_id})')

    else:
        # User wants to upload a new beatmapset
        if remaining_beatmaps <= 0:
            app.session.logger.warning(f'Failed to create beatmapset: User has no remaining beatmap uploads')
            return error_response(5, "You have reached your maximum amount of beatmaps you can upload.")

        # Create a new empty beatmapset inside the database
        set_id, beatmap_ids = create_beatmapset(
            user,
            beatmap_ids,
            session=session
        )

        if set_id is None:
            return error_response(5, "An error occurred while creating the beatmapset.")
        
        app.session.logger.info(f'{user.name} wants to create a new beatmapset ({set_id})')

    # Either we don't have the osz2 file or the client has no osz2 file
    # If full-submit is true, the client will submit a patch file
    full_submit = is_full_submit(set_id, osz2_hash)

    return Response('\n'.join([
        '0',
        f'{set_id}',
        ','.join(map(str, beatmap_ids)),
        f'{int(full_submit)}',
        f'{remaining_beatmaps}',
        f'{int(bubbled)}'
    ]))

@router.post('/osu-osz2-bmsubmit-upload.php')
def upload_beatmap(
    session: Session = Depends(app.session.database.yield_session),
    submission_file: UploadFile = Depends(file('0', 'osz2')),
    full_submit: bool = Depends(integer_boolean('t')),
    osz2_hash: str = Depends(query_or_form('z')),
    username: str = Depends(query_or_form('u')),
    password: str = Depends(query_or_form('h')),
    set_id: int = Depends(query_or_form('s'))
) -> Response:
    if not config.OSZ2_SERVICE_URL:
        app.session.logger.warning('The osz2-service url was not found. Aborting...')
        return error_response(5, 'The beatmap submission system is currently disabled. Please try again later!')

    error, user = authenticate_user(
        username,
        password,
        session=session
    )

    if error:
        # Failed to authenticate user
        return error

    beatmapset = beatmapsets.fetch_one(set_id, session)

    if not beatmapset:
        app.session.logger.warning(f'Failed to upload beatmap: Beatmapset not found')
        return error_response(5, 'The beatmapset you are trying to upload to does not exist. Please try again!')

    if beatmapset.creator_id != user.id:
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

    osz2_file = submission_file.file.read()

    if len(osz2_file) > 100_000_000: # 100mb
        app.session.logger.warning(f'Failed to upload beatmap: osz2 file is too large')
        return error_response(5, 'Your beatmap is too big. Try to reduce its filesize and try again!')

    if not full_submit:
        # User uploaded a patch file
        current_osz2_file = app.session.storage.get_osz2_internal(set_id)

        if not current_osz2_file:
            app.session.logger.warning(f'Failed to upload beatmap: Full submit requested but osz2 file is missing')
            return error_response(5, 'The osz2 file is missing. Please try again!')

        # Apply the patch to the current osz2 file
        osz2_file = beatmap_helper.patch_osz2(
            osz2_file,
            current_osz2_file
        )

    if not osz2_file:
        app.session.storage.remove_osz2(set_id)
        app.session.logger.warning(f'Failed to upload beatmap: Failed to read osz2 file ({full_submit})')
        return error_response(5, 'Something went wrong while processing your beatmap. Please try again!')

    # Decrypt osz2 file
    data = beatmap_helper.decrypt_osz2(osz2_file)

    if not data:
        app.session.storage.remove_osz2(set_id)
        app.session.logger.warning(f'Failed to upload beatmap: Failed to decrypt osz2 file')
        return error_response(5, 'Something went wrong while processing your beatmap. Please try again!')

    try:
        # Decode beatmap files
        files = {
            filename: base64.b64decode(content)
            for filename, content in data['files'].items()
        }

        # Check if the user is trying to upload someone else's beatmap
        if duplicate_beatmap_files(files, user.id, session):
            app.session.logger.warning(f'Failed to upload beatmap: Duplicate beatmap files')
            return error_response(5, 'It seems like one of your beatmaps was already uploaded by someone else. Please try again!')

        if not validate_beatmap_owner(data['beatmaps'], data['metadata'], user):
            app.session.logger.warning(f'Failed to upload beatmap: User does not own the beatmapset')
            return error_response(1)

        max_beatmap_length = max(
            beatmap['totalLength'] / 1000
            for beatmap in data['beatmaps'].values()
        )

        if max_beatmap_length <= 1:
            app.session.logger.warning(f'Failed to upload beatmap: Beatmap length is too short')
            return error_response(5, 'Your beatmap is too short. Please try to make it longer and try again!')

        package_filesize = calculate_package_size(files)
        size_limit = calculate_size_limit(max_beatmap_length)

        if package_filesize > size_limit and not user.is_admin:
            app.session.logger.warning(f'Failed to upload beatmap: Beatmap package is too large')
            return error_response(5, 'Your beatmap is too big. Try to reduce its filesize and try again!')

        previous_status = beatmapset.status

        # Update metadata for beatmapset and beatmaps
        update_beatmap_metadata(
            beatmapset,
            files,
            data['metadata'],
            data['beatmaps'],
            session
        )

        # Create & upload .osz file
        update_beatmap_package(
            set_id,
            files,
            session=session
        )

        # Update beatmap assets
        update_beatmap_thumbnail(set_id, files, data['beatmaps'])
        update_beatmap_audio(set_id, files, data['beatmaps'])
        update_beatmap_files(files, session=session)

        # Upload the osz2 file to storage
        app.session.storage.upload_osz2(set_id, osz2_file)

        # Update osz2 hashes
        update_osz2_hashes(set_id, osz2_file, session)
    except Exception as e:
        session.rollback()
        app.session.logger.error(f'Failed to upload beatmap: Failed to process osz2 file ({e})', exc_info=True)
        return error_response(5, 'Something went wrong while processing your beatmap. Please try again!')

    app.session.logger.info(
        f'{user.name} successfully {"uploaded" if full_submit else "updated"} a beatmapset '
        f'(http://osu.{config.DOMAIN_NAME}/s/{set_id})'
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
    error, user = authenticate_user(
        username,
        password,
        session=session
    )

    if error:
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
) -> Response:
    error, user = authenticate_user(
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

    if not (topic := topics.fetch_one(beatmapset.topic_id, session)):
        app.session.logger.warning(f'Failed to fetch beatmapset topic: Topic not found')
        return error_response(1)

    first_post = posts.fetch_initial_post(topic.id, session)

    return Response('\u0003'.join([
        f'0',
        f'{topic.id}',
        f'{topic.title}',
        f'{first_post.content if first_post else ""}',
    ]))

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
    parsed_beatmap: dict,
    has_video: bool,
    has_storyboard: bool,
    session: Session
) -> str | None:
    # Delete any inactive beatmaps
    delete_inactive_beatmaps(user, session=session)

    # Ensure that the user has no pending uploads
    beatmap_helper.remove_upload_request(user.id)

    osz_ticket = create_ticket_hash(
        beatmap_filename,
        user.id,
        is_osz=True
    )

    lazer_metadata = parsed_beatmap['metadata']
    metadata = beatmap_helper.format_metadata(lazer_metadata)

    request = beatmap_helper.UploadRequest(
        set_id,
        osz_ticket,
        has_video,
        has_storyboard,
        metadata
    )

    # Resolve set id through filename to prevent potential errors
    existing_beatmap = beatmaps.fetch_by_file(
        beatmap_filename,
        session=session
    )

    if existing_beatmap:
        request.set_id = existing_beatmap.set_id

    beatmap_helper.register_upload_request(user.id, request)

def handle_common_upload(
    upload_request: beatmap_helper.UploadRequest | None,
    beatmap_file: bytes,
    beatmap_filename: str,
    parsed_beatmap: dict,
    user: DBUser,
    session: Session
) -> str | None:
    beatmap_ticket = create_ticket_hash(
        beatmap_filename,
        user.id
    )

    upload_ticket = beatmap_helper.UploadTicket(
        beatmap_filename,
        beatmap_ticket,
        beatmap_file,
        parsed_beatmap,
    )

    upload_request.tickets.append(upload_ticket)

    beatmapset = beatmapsets.fetch_one(upload_request.set_id, session)
    response = ["old"]

    if not beatmapset:
        # User wants to upload a new beatmapset
        response = ["new"]

        # Create a new empty beatmapset inside the database
        upload_request.set_id, _ = create_beatmapset(
            user, [],
            session=session
        )

        if upload_request.set_id is None:
            app.session.logger.warning(f'Failed to create beatmapset: set_id is None')
            return "An error occurred while creating the beatmapset."

    # Update upload request
    beatmap_helper.register_upload_request(
        user.id,
        upload_request
    )

    if beatmapset:
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

    if response[0] != "new":
        is_approved = beatmapset.status > 0
        response.append(f'{beatmapset.topic_id or -1}')
        response.append(f'{int(is_approved)}')
        response.append(post.topic.title)
        response.append(post.content)

    return '\n'.join(response)

def handle_upload_finish(user: DBUser, session: Session) -> str | None:
    request = beatmap_helper.get_upload_request(user.id)

    if not request:
        app.session.logger.warning(f'Failed to process upload request: Upload request not found')
        return "An error occurred while processing your beatmap. Please try again!"

    remaining_beatmaps = remaining_beatmap_uploads(user, session)
    beatmapset = beatmapsets.fetch_one(request.set_id, session)

    if not beatmapset:
        app.session.logger.warning(f'Failed to process upload request: Beatmapset not found')
        return "An error occurred while creating the beatmapset. Please try again!"

    if beatmapset.status == -3 and remaining_beatmaps <= 0:
        app.session.logger.warning(f'Failed to create beatmapset: User has no remaining beatmap uploads')
        return "You have reached your maximum amount of beatmaps you can upload."
        
    if beatmapset.creator_id != user.id:
        app.session.logger.warning(f'Failed to process upload request: User does not own the beatmapset')
        return error_response(1, legacy=True)
    
    if beatmapset.server != 1:
        app.session.logger.warning(f'Failed to process upload request: Beatmapset is not on Titanic')
        return error_response(1, legacy=True)
    
    if beatmapset.status > 0:
        app.session.logger.warning(f'Failed to process upload request: Beatmapset is ranked or loved')
        return error_response(3, legacy=True)
    
    if beatmapset.status == -2:
        app.session.logger.warning(f'Failed to process upload request: Beatmapset is graveyarded')
        return error_response(4, legacy=True)

    if duplicate_beatmap_files(request.files, user.id, session):
        app.session.logger.warning(f'Failed to process upload request: Duplicate beatmap files')
        return "It seems like one of your beatmaps was already uploaded by someone else. Please try again!"
    
    if not validate_beatmap_owner(request.beatmaps, request.metadata, user):
        app.session.logger.warning(f'Failed to process upload request: User does not own the beatmapset')
        return error_response(1, legacy=True)

    previous_osz = app.session.storage.get_osz_internal(beatmapset.id)
    previous_osz = previous_osz or empty_zip_file()

    # Read all files of previous osz
    with ZipFile(io.BytesIO(previous_osz)) as zip_file:
        files = {
            filename: zip_file.read(filename)
            for filename in zip_file.namelist()
        }

    # Add updated maps to the files
    for filename, content in request.files.items():
        files[filename] = content

    max_beatmap_length = max(
        beatmap['totalLength'] / 1000
        for beatmap in request.beatmaps.values()
    )

    if max_beatmap_length <= 1:
        app.session.logger.warning(f'Failed to upload beatmap: Beatmap length is too short')
        return "Your beatmap is too short. Please try to make it longer and try again!"

    package_filesize = calculate_package_size(files)
    size_limit = calculate_size_limit(max_beatmap_length)

    if package_filesize > size_limit:
        app.session.logger.warning(f'Failed to upload beatmap: Beatmap package is too large')
        return "Your beatmap is too big. Try to reduce its filesize and try again!"

    has_full_submit = not all(
        filename.endswith('.osu')
        for filename in files
    )

    beatmap_ids = [
        beatmaps.fetch_id_by_filename(ticket.filename, session) or -1
        for ticket in request.tickets
    ]

    # Create/Remove new beatmaps if necessary
    beatmap_ids = update_beatmaps(
        beatmap_ids,
        beatmapset,
        session=session
    )

    # Update relationships
    session.refresh(beatmapset)

    # Update metadata for beatmapset and beatmaps
    update_beatmap_metadata(
        beatmapset,
        files,
        request.metadata,
        request.beatmaps,
        session
    )

    # Update .osz file
    update_beatmap_package(
        beatmapset.id,
        files,
        session
    )

    # Update beatmap files
    update_beatmap_files(
        request.files,
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

@router.post('/osu-bmsubmit-getid5.php')
@router.post('/osu-bmsubmit-getid4.php')
@router.post('/osu-bmsubmit-getid3.php')
@router.post('/osu-bmsubmit-getid2.php')
@router.post('/osu-bmsubmit-getid.php')
def update_beatmap_files_endpoint(
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p'),
    set_id: int = Query(-1, alias='s'),
    action: SendAction = Query(..., alias='r'),
    has_video: bool = Depends(integer_boolean_query('v')),
    has_storyboard: bool = Depends(integer_boolean_query('sb')),
    beatmap_file: UploadFile = File(..., alias='osu'),
    session: Session = Depends(app.session.database.yield_session)
) -> Response:
    error, user = authenticate_user(
        username,
        password,
        session=session,
        legacy=True
    )

    if error:
        # Failed to authenticate user
        return error

    beatmap_file_contents = beatmap_file.file.read()
    beatmap_filename = beatmap_file.filename

    if len(beatmap_file_contents) > 15_000_000: # 15mb
        return "Your beatmap is too big. Try to reduce its filesize and try again!"

    # Parse beatmap file
    parsed_beatmap = beatmap_helper.parse_beatmap(beatmap_file_contents)

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

    upload_request = beatmap_helper.get_upload_request(user.id)

    if not upload_request:
        app.session.logger.warning(f'Failed to process upload request: Upload request not found')
        return "An error occurred while processing your beatmap. Please try again!"

    # Create a ticket for the given beatmap
    response_data = handle_common_upload(
        upload_request,
        beatmap_file_contents,
        beatmap_filename,
        parsed_beatmap,
        user, session
    )

    if not response_data:
        return "An error occurred while processing your beatmap. Please try again!"

    if action in (SendAction.LastBeatmap, SendAction.SingleBeatmap):
        # Validate all beatmaps, update metadata,
        # upload new files, ...
        error = handle_upload_finish(
            user,
            session
        )

        if error:
            return error

    return response_data

@router.post('/osu-bmsubmit-upload.php')
def upload_osz(
    username: str = Query(..., alias='u'),
    password: str = Query(..., alias='p'),
    ticket: str = Query(..., alias='c'),
    osz_filename: str = Query(..., alias='of'),
    osz_ticket: str = Query(..., alias='oc'),
    file: UploadFile = File(..., alias='osu'),
    set_id: int | None = Query(None, alias='s'),
    is_first: bool = Depends(integer_boolean_query('r')),
    session: Session = Depends(app.session.database.yield_session)
) -> Response:
    error, user = authenticate_user(
        username,
        password,
        session=session,
        legacy=True
    )

    if error:
        # Failed to authenticate user
        return Response(error.body, 403)
    
    if not (upload_request := beatmap_helper.get_upload_request(user.id)):
        app.session.logger.warning(f'Failed to upload osz file: Upload request not found')
        return bancho_message("An error occurred while processing your beatmap. Please try again!", user)

    # Ensure set_id has a value - some clients don't send it
    set_id = set_id or upload_request.set_id

    if set_id != upload_request.set_id:
        app.session.logger.warning(f'Failed to upload osz file: Invalid set id')
        return bancho_message("An error occurred while processing your beatmap. Please try again!", user)

    if osz_ticket != upload_request.osz_ticket:
        app.session.logger.warning(f'Failed to upload osz file: Invalid ticket')
        return bancho_message("An error occurred while processing your beatmap. Please try again!", user)

    if ticket != upload_request.osz_ticket:
        # We already updated all beatmap files
        # so we can just return here.
        return "ok"

    # Remove ticket, as it's no longer needed
    beatmap_helper.remove_upload_request(user.id)

    osz_file = ZipFile(file.file)
    files = {
        filename: osz_file.read(filename)
        for filename in osz_file.namelist()
    }

    osz_map_files = [
        filename
        for filename in files
        if filename.endswith('.osu')
    ]

    # Ensure we got the same amount of beatmaps
    if len(osz_map_files) != len(upload_request.tickets):
        app.session.logger.warning(f'Failed to upload osz file: Invalid amount of beatmaps')
        return bancho_message("An error occurred while processing your beatmap. Please try again!", user)

    # Check if osz beatmap files are present in upload ticket
    # and compare them with the uploaded osz file
    for filename, content in upload_request.files.items():
        if filename not in files:
            app.session.logger.warning(f'Failed to upload osz file: Missing beatmap file')
            return bancho_message("An error occurred while processing your beatmap. Please try again!", user)
        
        ticket_hash = hashlib.md5(content).hexdigest()
        file_hash = hashlib.md5(files[filename]).hexdigest()
        
        if ticket_hash != file_hash:
            app.session.logger.warning(f'Failed to upload osz file: Beatmap hash mismatch')
            return bancho_message("An error occurred while processing your beatmap. Please try again!", user)

    max_beatmap_length = max(
        beatmap['totalLength'] / 1000
        for beatmap in upload_request.beatmaps.values()
    )

    if max_beatmap_length <= 1:
        app.session.logger.warning(f'Failed to upload beatmap: Beatmap length is too short')
        return bancho_message("Your beatmap is too short. Please try to make it longer and try again!", user)

    package_filesize = calculate_package_size(files)
    size_limit = calculate_size_limit(max_beatmap_length)

    if package_filesize > size_limit:
        app.session.logger.warning(f'Failed to upload beatmap: Beatmap package is too large')
        return bancho_message("Your beatmap is too big. Try to reduce its filesize and try again!", user)

    beatmapset = beatmapsets.fetch_one(set_id, session)
    previous_status = beatmapset.status

    # Update metadata for beatmapset and beatmaps
    update_beatmap_metadata(
        beatmapset,
        files,
        upload_request.metadata,
        upload_request.beatmaps,
        session=session
    )

    # Create & upload .osz file
    update_beatmap_package(
        set_id,
        files,
        session=session
    )

    # Update beatmap assets
    update_beatmap_thumbnail(set_id, files, upload_request.beatmaps)
    update_beatmap_audio(set_id, files, upload_request.beatmaps)
    update_beatmap_files(files, session=session)

    app.session.logging.info(
        f'{user.name} uploaded an osz file for beatmapset ({set_id})'
    )

    # Depending on if the beatmap is new or updated, different event types should be used
    broadcast_type = broadcast_upload_activity if previous_status == -3 else broadcast_update_activity
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
    error, user = authenticate_user(
        username,
        password,
        session=session,
        legacy=True
    )

    if error:
        return Response(status_code=403)

    # Remove upload request
    beatmap_helper.remove_upload_request(user.id)

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
            not complete, bumprequest,
            session=session
        )
        return Response(f'{topic_id}')

    if not (topic := topics.fetch_one(beatmapset.topic_id, session)):
        topic_id = create_beatmap_topic(
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
