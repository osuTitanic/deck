
from typing import Dict, List, Tuple, Iterable
from zipfile import ZipFile, ZipInfo
from slider.events import EventType
from sqlalchemy.orm import Session
from collections import Counter
from datetime import datetime
from fastapi import Response
from sqlalchemy import func
from slider import Beatmap
from osz2 import *

from .bss_decorators import *
from .bss_tickets import *
from .bss_osz2 import *

from app.common.helpers import activity, performance, permissions as permissions_helper
from app.common.constants import UserActivity, BeatmapGenre, BeatmapLanguage
from app.common.database.repositories import *
from app.common.database.objects import *
from app.common.config import config_instance as config
from app.common.cache import status
from app.common import officer
from app.helpers import bss
from app import utils

import urllib.parse
import statistics
import hashlib
import zipfile
import math
import stat
import app
import io

allowed_file_extensions = (
    ".osu", ".osz", ".osb", ".osk", ".png", ".mp3", ".jpeg",
    ".wav", ".png", ".wav", ".ogg", ".jpg", ".wmv", ".flv",
    ".mp3", ".flac", ".mp4", ".avi", ".ini", ".jpg", ".m4v",
    ".mpg", ".mov", ".webm", ".mkv", ".ogv", ".mpeg", ".3gp"
)
video_file_extensions = (
    ".wmv", ".flv", ".mp4",
    ".avi", ".m4v", ".mpg",
    ".mov", ".webm", ".mkv",
    ".ogv", ".mpeg", ".3gp"
)

LanguageMapping = {
    BeatmapLanguage(language_id).name.lower(): BeatmapLanguage(language_id)
    for language_id in BeatmapLanguage.values()
}
GenreMapping = {
    BeatmapGenre(genre_id).name.lower(): BeatmapGenre(genre_id)
    for genre_id in BeatmapGenre.values()
}

def authenticate_user(
    username: str,
    password: str,
    session: Session,
    legacy: bool = False
) -> Tuple[Response | None, DBUser | None]:
    """Authenticate the user with the given username and password"""
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

    if not permissions_helper.has_permission("beatmaps.upload", player.id):
        app.session.logger.warning(f'Failed to authenticate user: User lacks beatmap upload permission')
        return error_response(5, 'You do not have permission to upload beatmaps.', legacy), None

    return None, player

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

def bancho_message(message: str, user: DBUser) -> Response:
    """Send a message to the user via. the announce packet in bancho"""
    app.session.events.submit(
        'user_announcement',
        user_id=user.id,
        message=message,
    )
    return Response(message, 400)

def is_full_submit(set_id: int, osz2_hash: str) -> bool:
    """Determine if the client should upload the full osz2 or a patch file"""
    if not config.BEATMAP_SUBMISSION_STORE_OSZ2:
        # We don't store osz2 files, so the client should always upload the full osz2
        return True

    if not osz2_hash:
        # Client has no osz2 it can patch
        return True

    osz2_file = app.session.storage.get_osz2(set_id)

    if not osz2_file:
        # We don't have an osz2 we can patch
        return True

    # Check if osz2 file is outdated
    return osz2_hash != hashlib.md5(osz2_file).hexdigest()

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
    return int(counter.most_common(1)[0][0]) if counter else 0

def update_beatmap_metadata(
    beatmapset: DBBeatmapset,
    files: List[File],
    metadata: Dict[MetadataType, str | float | None],
    beatmap_data: Dict[str, Beatmap],
    session: Session
) -> None:
    app.session.logger.debug(f'Updating beatmap metadata...')

    file_extensions = [
        file.file_extension
        for file in files
    ]

    # Map is in "wip", until the user posts it to the forums
    status = (-1 if beatmapset.status <= -1 else 0)

    # Try to detect genre & language from tags
    tags = metadata.get(MetadataType.Tags, '').split() # type: ignore this shit
    detected_language = bss.detect_language_from_tags(tags)
    detected_genre = bss.detect_genre_from_tags(tags)
    is_explicit = bss.detect_explicit_from_tags(tags) or beatmapset.explicit

    # Check if any of the individual beatmaps has storyboard elements
    has_storyboard_elements = any([
        [
            event for event in beatmap.events
            if event.event_type in {EventType.Sprite, EventType.Animation}
        ]
        for beatmap in beatmap_data.values()
    ])

    # Update beatmapset metadata
    beatmapsets.update(
        beatmapset.id,
        {
            'artist': metadata.get(MetadataType.Artist),
            'title': metadata.get(MetadataType.Title),
            'creator': metadata.get(MetadataType.Creator),
            'source': metadata.get(MetadataType.Source),
            'tags': metadata.get(MetadataType.Tags),
            'artist_unicode': metadata.get(MetadataType.ArtistUnicode),
            'title_unicode': metadata.get(MetadataType.TitleUnicode),
            'source_unicode': metadata.get(MetadataType.SourceUnicode),
            'has_video': any(ext in file_extensions for ext in bss.video_file_extensions),
            'explicit': is_explicit,
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
                f'[bold:0,size:20]{metadata.get(MetadataType.Artist, "")}|'
                f'[]{metadata.get(MetadataType.Title, "")}'
            ),
            'has_storyboard': (
                'osb' in file_extensions or
                has_storyboard_elements
            ),
            'last_update': datetime.now(),
            'status': status
        },
        session=session
    )

    beatmap_files = {
        file.filename: file
        for file in files
        if file.is_beatmap
    }

    beatmap_ids = sorted([
        beatmap.id
        for beatmap in beatmapset.beatmaps
    ])
    assert len(beatmap_ids) >= len(beatmap_data), "More beatmaps provided than expected"

    # Before updating the beatmap metadata, we first have to
    # assign all beatmap IDs, such that the IDs won't be shuffled
    pre_assigned_ids = []

    for filename, beatmap in beatmap_data.items():
        if beatmap.beatmap_id is not None:
            pre_assigned_ids.append(beatmap.beatmap_id)
            continue

        beatmap_id = resolve_beatmap_id(
            beatmap_ids,
            beatmap,
            filename,
            session=session
        )
        assert beatmap_id is not None
        beatmap.beatmap_id = beatmap_id

    # Check for duplicate pre-assigned IDs
    assert len(pre_assigned_ids) == len(set(pre_assigned_ids)), "Duplicate beatmap IDs"

    # Ensure the pre-assigned IDs are part of the beatmapset
    for beatmap_id in pre_assigned_ids:
        assert beatmap_id in beatmap_ids, "Beatmap ID not part of beatmapset"

    for filename, beatmap in beatmap_data.items():
        difficulty_attributes = performance.calculate_difficulty(
            beatmap_files[filename].content,
            beatmap.mode # type: ignore
        )
        assert difficulty_attributes is not None, "Failed to calculate beatmap difficulty"

        # I'm not too sure if this is the way to go when working with slider, but I guess this works for now
        count_normal = len(beatmap.hit_objects(circles=True, sliders=False, spinners=False))
        count_slider = len(beatmap.hit_objects(sliders=True, circles=False, spinners=False))
        count_spinner = len(beatmap.hit_objects(spinners=True, circles=False, sliders=False))

        assert beatmap.beatmap_id is not None, "Beatmap ID is None" # should never happen, we pre-assigned all IDs above

        beatmaps.update(
            beatmap.beatmap_id,
            {
                'status': status,
                'filename': filename,
                'last_update': datetime.now(),
                'md5': hashlib.md5(beatmap_files[filename].content).hexdigest(),
                'bpm': bss.calculate_beatmap_median_bpm(beatmap),
                'drain_length': round(bss.calculate_beatmap_drain_length(beatmap) / 1000),
                'total_length': round(bss.calculate_beatmap_total_length(beatmap) / 1000),
                'version': beatmap.version or 'Normal',
                'mode': beatmap.mode,
                'hp': beatmap.hp(),
                'cs': beatmap.cs(),
                'od': beatmap.od(),
                'ar': beatmap.ar(),
                'slider_multiplier': beatmap.slider_multiplier,
                'count_normal': count_normal,
                'count_slider': count_slider,
                'count_spinner': count_spinner,
                'max_combo': difficulty_attributes.max_combo,
                'diff': difficulty_attributes.star_rating
            },
            session=session
        )

    # Refresh beatmapset object & check for
    # remaining inactive beatmaps
    session.refresh(beatmapset)

    for beatmap in beatmapset.beatmaps:
        if beatmap.status == -3:
            # Remove inactive beatmap
            plays.delete_by_beatmap_id(beatmap.id, session=session)
            beatmaps.delete_by_id(beatmap.id, session=session)
            continue

        # Update eyup stars for ppv1 calculations
        eyup_difficulty = performance.calculate_eyup_star_rating(beatmap)
        assert eyup_difficulty is not None, "Failed to calculate eyup difficulty"
        assert not math.isinf(eyup_difficulty), "Eyup difficulty is infinite"
        assert not math.isnan(eyup_difficulty), "Eyup difficulty is NaN"

        # Rounding to 4 decimal places for database
        eyup_difficulty = round(eyup_difficulty, 4)
        eyup_difficulty = float(eyup_difficulty)
        beatmaps.update(beatmap.id, {'diff_eyup': eyup_difficulty}, session=session)

    if is_bubbled(beatmapset, session):
        # Bubble should be popped when the beatmap
        # gets updated. It will re-gain 5 star priority
        pop_bubble(beatmapset, session)

def update_beatmap_thumbnail(
    beatmapset: DBBeatmapset,
    beatmaps: Dict[str, Beatmap],
    files: List[File]
) -> None:
    app.session.logger.debug(f'Uploading beatmap thumbnail...')

    # Delete cached thumbnails
    app.session.redis.delete(f'mt:{beatmapset.id}', f'mt:{beatmapset.id}l')

    filenames = [
        file.filename
        for file in files
    ]

    background_files = [
        beatmap.backgrounds[0]
        for beatmap in beatmaps.values()
        if beatmap.backgrounds
    ]

    if not background_files:
        app.session.logger.debug(f'Background file not specified. Skipping...')
        return

    target_background = background_files[0]

    if target_background.filename not in filenames:
        app.session.logger.debug(f'Background file not found. Skipping...')
        return

    background_file = next(
        file for file in files
        if file.filename == target_background.filename
    )
    thumbnail = app.utils.resize_and_crop_image(
        background_file.content,
        target_width=160,
        target_height=120
    )

    app.session.storage.upload_background(
        beatmapset.id,
        thumbnail
    )

def update_beatmap_audio(
    beatmapset: DBBeatmapset,
    beatmaps: Dict[str, Beatmap],
    files: List[File]
) -> None:
    app.session.logger.debug(f'Uploading beatmap audio preview...')

    # Delete cached preview
    app.session.redis.delete(f'mp3:{beatmapset.id}')

    beatmaps_with_audio = [
        beatmap
        for beatmap in beatmaps.values()
        if beatmap.audio_filename
    ]

    if not beatmaps_with_audio:
        app.session.logger.debug(f'Audio file not specified. Skipping...')
        return

    target_beatmap = beatmaps_with_audio[0]
    audio_filename = target_beatmap.audio_filename
    audio_offset = target_beatmap.preview_time.total_seconds() * 1000

    audio_file = next(
        (file for file in files if file.filename == audio_filename),
        None
    )

    if not audio_file:
        app.session.logger.debug(f'Audio file not found. Skipping...')
        return

    audio_snippet = utils.extract_audio_snippet(
        audio_file.content,
        offset_ms=audio_offset,
        bitrate="128k"
    )

    app.session.storage.upload_mp3(
        beatmapset.id,
        audio_snippet
    )

def update_beatmap_files(files: List[File], session: Session) -> None:
    app.session.logger.debug(f'Uploading beatmap files...')

    for file in files:
        if not file.is_beatmap:
            continue

        try:
            beatmap_id = beatmaps.fetch_id_by_filename(file.filename, session)
        except Exception as e:
            app.session.logger.error(f'Failed to fetch beatmap id for file "{file.filename}": {e}')
            continue

        if not beatmap_id:
            app.session.logger.warning(f'Beatmap file "{file.filename}" not found in database. Skipping...')
            continue

        app.session.storage.upload_beatmap_file(
            beatmap_id,
            file.content
        )

def update_beatmap_package(
    set_id: int,
    files: List[File],
    osz_package: bytes,
    session: Session
) -> None:
    app.session.logger.debug(f'Updating beatmap package...')

    osz_size = len(osz_package)

    app.session.storage.upload_osz(
        set_id,
        osz_package
    )

    # Get total length of all video files
    video_files = [
        file for file in files
        if any(file.filename.endswith(ext) for ext in bss.video_file_extensions)
    ]

    total_video_length = sum(
        len(file.content)
        for file in video_files
    )
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

def duplicate_beatmap_files(
    beatmapset: DBBeatmapset,
    files: List[File],
    session: Session
) -> bool:
    """Check for duplicate beatmap filenames & checksums"""
    for file in files:
        if not file.is_beatmap:
            continue

        if beatmap := beatmaps.fetch_by_file(file.filename, session):
            if beatmap.beatmapset.creator_id != beatmapset.creator_id:
                return True

        file_checksum = hashlib.md5(file.content).hexdigest()

        if beatmap := beatmaps.fetch_by_checksum(file_checksum, session):
            if beatmap.beatmapset.creator_id != beatmapset.creator_id:
                return True

    return False

def validate_beatmap_owner(
    metadata: Dict[MetadataType, str | float | None],
    beatmaps: Dict[str, Beatmap],
    allowed_usernames: Iterable[str]
) -> bool:
    creator = metadata.get(MetadataType.Creator)
    assert isinstance(creator, str) or creator is None

    if creator and creator not in allowed_usernames:
        return False

    for beatmap in beatmaps.values():
        if beatmap.creator not in allowed_usernames:
            return False

    return True

def resolve_beatmap_id(
    beatmap_ids: List[int],
    beatmap: Beatmap,
    filename: str,
    session: Session
) -> int:
    # Newer .osu version have the beatmap id in the metadata
    if (beatmap_id := beatmap.beatmap_id) is not None:
        if beatmap_id in beatmap_ids:
            beatmap_ids.remove(beatmap_id)
            return beatmap_id

    # Try to get the beatmap id from the filename
    if beatmap_object := beatmaps.fetch_by_file(filename, session):
        if beatmap_object.id in beatmap_ids:
            beatmap_ids.remove(beatmap_object.id)
            return beatmap_object.id

    # Beatmap has not been uploaded yet, return a new id
    return beatmap_ids.pop(0)

def is_bubbled(beatmapset: DBBeatmapset, session: Session) -> bool:
    """Check if a beatmap has the 'bubble' icon on the forums"""
    if not beatmapset.topic_id:
        return False

    topic = topics.fetch_one(
        beatmapset.topic_id,
        session=session
    )
    # TODO: replace with nomination checks

    return (
        topic.icon_id == 3
        if topic else False
    )

def pop_bubble(beatmapset: DBBeatmapset, session: Session) -> None:
    """Change the forum icon of the beatmap and increase its star priority by 5"""
    if not beatmapset.topic_id:
        return

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

def delete_inactive_beatmaps(user: DBUser, session: Session) -> None:
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
            for beatmap in set.beatmaps:
                collaborations.delete_requests_by_beatmap(beatmap.id, session=session)
                collaborations.delete_by_beatmap(beatmap.id, session=session)

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
            if set.topic_id is None:
                continue

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
    """Calculate how many more beatmaps the user can upload"""
    user_groups = groups.fetch_user_groups(
        user.id,
        include_hidden=True,
        session=session
    )

    group_names = [group.name for group in user_groups]

    if 'Admins' in group_names:
        # Admins have unlimited uploads
        return 69

    if 'Beatmap Approval Team' in group_names:
        # BATs have unlimited uploads
        return 69

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
    """Create a new beatmapset with the given beatmaps"""
    # Create new beatmapset
    set = beatmapsets.create(
        id=bss.next_beatmapset_id(session=session),
        creator=user.name,
        creator_id=user.id,
        server=1
    )

    # Create beatmaps
    new_beatmaps = [
        beatmaps.create(
            id=bss.next_beatmap_id(session=session),
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
    user: DBUser,
    beatmap_ids: List[int],
    beatmapset: DBBeatmapset,
    session: Session
) -> List[int] | None:
    """Create/Delete beatmaps based on the amount of beatmaps the client requested"""
    # Get current beatmaps
    current_beatmap_ids = [
        beatmap.id
        for beatmap in beatmapset.beatmaps
    ]
    beatmaps_deleted = (
        len(beatmap_ids) < len(current_beatmap_ids)
    )

    # Check if beatmap ids are valid & part of the set
    for index, beatmap_id in (enumerate(beatmap_ids)):
        if beatmap_id <= -1:
            continue

        if beatmap_id in current_beatmap_ids:
            continue

        # We need to recreate this ID, since its
        # not part of the current beatmapset
        beatmap_ids[index] = -1

    if beatmaps_deleted:
        # Beatmaps have been deleted by the uploader
        # -> Remove them from the database
        deleted_maps = [
            beatmap_id
            for beatmap_id in current_beatmap_ids
            if beatmap_id not in beatmap_ids
        ]

        for beatmap_id in deleted_maps:
            is_collaborator = beatmapset.creator_id != user.id

            if is_collaborator:
                app.session.logger.warning(f'User {user.name} tried to delete beatmap {beatmap_id} without permission')
                return None

            collaborations.delete_by_beatmap(beatmap_id, session=session)
            plays.delete_by_beatmap_id(beatmap_id, session=session)
            beatmaps.delete_by_id(beatmap_id, session=session)

        app.session.logger.debug(f'Deleted beatmaps: {deleted_maps}')
        return beatmap_ids

    # User is adding new beatmaps
    # -> Create entry in the database to get the ID
    is_collaborator = beatmapset.creator_id != user.id
    beatmaps_created = []

    for index, beatmap_id in enumerate(beatmap_ids):
        if beatmap_id != -1:
            continue

        # Create new beatmap
        new_beatmap = beatmaps.create(
            id=bss.next_beatmap_id(session=session),
            set_id=beatmapset.id,
            session=session
        )

        # Add collaborator permissions, if user is not the creator
        if is_collaborator:
            collaborations.create(
                new_beatmap.id, user.id,
                is_beatmap_author=True,
                allow_resource_updates=True,
                session=session
            )

        beatmap_ids[index] = new_beatmap.id
        beatmaps_created.append(new_beatmap.id)

    # Return new beatmap ids to the client
    app.session.logger.debug(f'Created new beatmaps: {beatmaps_created}')
    return beatmap_ids

def update_osz2_hashes(set_id: int, osz2: Osz2Package, session: Session) -> None:
    """Update the osz2 hashes for the given beatmapset & osz2"""
    beatmapsets.update(
        set_id,
        {
            'meta_hash': osz2.metadata_hash.hex(),
            'info_hash': osz2.file_info_hash.hex(),
            'body_hash': osz2.full_body_hash.hex()
        },
        session=session
    )

def resolve_beatmapset(
    set_id: int,
    beatmap_ids: List[int],
    session: Session
) -> DBBeatmapset | None:
    """Resolve the beatmapset either by set ID or beatmap IDs"""
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

def beatmap_update_permissions(
    user: DBUser,
    beatmapset: DBBeatmapset,
    session: Session
) -> Tuple[List[DBBeatmap], bool]:
    """Check which beatmaps the user is allowed to update"""
    if user.id == beatmapset.creator_id:
        # User is the creator of the beatmapset
        return [beatmap for beatmap in beatmapset.beatmaps], True

    collaboration_entries = collaborations.fetch_by_beatmaps(
        [beatmap.id for beatmap in beatmapset.beatmaps],
        session=session
    )

    affected_collaborations = [
        entry for entry in collaboration_entries
        if entry.user_id == user.id
    ]

    if not affected_collaborations:
        # User is not a collaborator on any of the beatmaps
        return [], False

    can_update_resources = any([
        entry.allow_resource_updates
        for entry in affected_collaborations
    ])

    return [entry.beatmap for entry in affected_collaborations], can_update_resources

def adjust_files_for_collaboration(
    files: List[File],
    original_files: List[File],
    allowed_beatmaps: List[DBBeatmap],
    can_update_resources: bool
) -> List[File]:
    """Adjust the uploaded files based on what the user is allowed to update"""
    # Making sure that both files and original_files are not empty
    assert original_files and files, "Beatmap package files are empty"

    allowed_filenames = [
        beatmap.filename
        for beatmap in allowed_beatmaps
    ]

    beatmap_files = [
        file for file in files
        if file.filename in allowed_filenames
    ]

    original_beatmap_files = [
        file for file in original_files
        if file.is_beatmap
    ]

    resource_files = [
        file for file in files
        if not file.is_beatmap
    ]

    original_resource_files = [
        file for file in original_files
        if not file.is_beatmap
    ]

    if not can_update_resources:
        # User is only allowed to update their own beatmap files
        result_files = []
        result_files.extend(original_beatmap_files)
        result_files.extend(original_resource_files)
        result_files.extend(beatmap_files)
        return result_files

    new_beatmap_files = [
        file for file in files
        if file.is_beatmap
        and file not in original_beatmap_files
    ]

    # User is able to to update resources (e.g. images, audio, etc.)
    # as well as upload new beatmap files
    result_files = []
    result_files.extend(original_beatmap_files)
    result_files.extend(resource_files)
    result_files.extend(beatmap_files)
    result_files.extend(new_beatmap_files)
    return result_files

def existing_files(beatmapset_id: int) -> List[File]:
    previous_osz = app.session.storage.get_osz(beatmapset_id)
    previous_osz = previous_osz or utils.empty_zip_file()
    return bss.osz_to_files(previous_osz)

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
            f'[*][url={config.OSU_BASEURL}/web/maps/{urllib.parse.quote(beatmap.filename)}]{beatmap.version}[/url] '
            f'({round(beatmap.diff, 2)} stars)'
            for beatmap in beatmapset.beatmaps
        ),
        '[/list]',
        '',
        f'[size=150][b]Download: [url={config.OSU_BASEURL}/d/{beatmapset.id}]{beatmapset.artist} - {beatmapset.title}[/url][/b][/size]',
        f'[b]Information:[/b] [url={config.OSU_BASEURL}/s/{beatmapset.id}]Scores/Beatmap Listing[/url]',
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
        can_change_icon=True,
        status_text=(
            'Needs modding'
            if wip else
            'Waiting for BAT approval'
        ),
        session=session
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

# Reference:
# https://github.com/ppy/osu/blob/master/osu.Game/Beatmaps/Timing/BreakPeriod.cs

# The minimum gap between the start of the break and the previous object.
gap_before_break = 200

# The minimum gap between the end of the break and the next object.
gap_after_break = 450

# The minimum duration required for a break to have any effect.
min_break_duration = 650

# The minimum required duration of a gap between two objects such that a break can be placed between them.
minimum_gap = gap_before_break + min_break_duration + gap_after_break

def calculate_beatmap_total_length(beatmap: Beatmap) -> int | float:
    """Calculate the total length of a beatmap from its hit objects"""
    hit_objects = beatmap.hit_objects()

    if len(hit_objects) <= 1:
        return 0

    first_object = hit_objects[0].time.total_seconds() * 1000
    last_object = hit_objects[-1].time.total_seconds() * 1000
    return max(last_object - first_object, 0)

def calculate_beatmap_drain_length(beatmap: Beatmap) -> int | float:
    """Calculate the drain length of a beatmap from its hit objects"""
    hit_objects = beatmap.hit_objects()

    if len(hit_objects) <= 1:
        return 0

    # Identify every break in the beatmap and subtract it from the last object time
    # This also includes the break from the audio beginning to the first object
    last_object = hit_objects[-1].time.total_seconds() * 1000
    break_deltas = []

    for index, hit_object in enumerate(hit_objects):
        if index <= 0:
            continue

        previous_object = hit_objects[index - 1]
        delta_time = hit_object.time - previous_object.time
        delta_time_ms = delta_time.total_seconds() * 1000

        if delta_time_ms < minimum_gap:
            continue

        break_deltas.append(delta_time_ms - (min_break_duration + gap_after_break))

    total_break_time = sum(break_deltas)
    return max(last_object - total_break_time, 0)

def calculate_beatmap_median_bpm(beatmap: Beatmap) -> float:
    """Calculate the median BPM of a beatmap from its timing points"""
    bpm_values = (p.bpm for p in beatmap.timing_points if p.bpm)

    if not bpm_values:
        return 0.0

    return statistics.median(bpm_values)

def maximum_beatmap_length(beatmaps: Iterable[Beatmap]) -> int | float:
    """Retrieve the maximum total length of all beatmaps in milliseconds"""
    if not beatmaps:
        return 0

    return max(
        calculate_beatmap_total_length(beatmap)
        for beatmap in beatmaps
    )

def calculate_size_limit(beatmap_length: int | float) -> int | float:
    # The file size limit is 10MB plus an additional 10MB for
    # every minute of beatmap length, and it caps at 100MB.
    return min(
        10_000_000 + (10_000_000 * (beatmap_length / 60)),
        100_000_000
    )

def create_osz_package(files: List[File]) -> bytes:
    """Create an .osz package from a list of files"""
    buffer = io.BytesIO()
    osz = ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED)

    for file in files:
        # Create ZipInfo to set file metadata
        zip_info = ZipInfo(filename=file.filename_sanitized)
        zip_info.compress_type = zipfile.ZIP_DEFLATED
        zip_info.date_time = file.date_modified.timetuple()[:6]
        zip_info.external_attr = (stat.S_IFREG | 0o664) << 16
        osz.writestr(zip_info, file.content, compresslevel=1)

    osz.close()
    result = buffer.getvalue()

    del buffer
    del osz
    return result

def calculate_osz_size(files: List[File]) -> int:
    """Calculate the size of an .osz package from a list of files"""
    return len(create_osz_package(files))

def osz_to_files(osz_data: bytes) -> List[File]:
    """Extract files from an .osz package into osz2.File objects"""
    with ZipFile(io.BytesIO(osz_data)) as zip_file:
        files = []

        for info in zip_file.infolist():
            content = zip_file.read(info.filename)
            content_hash = hashlib.md5(content).digest()

            file = File(
                filename=info.filename,
                content=content,
                offset=info.header_offset,
                size=info.file_size,
                hash=content_hash,
                date_created=datetime(*info.date_time),
                date_modified=datetime(*info.date_time)
            )
            files.append(file)

    return files

def detect_language_from_tags(tags: List[str]) -> BeatmapLanguage:
    for tag in tags:
        filtered_tag = tag.lower().strip(",").strip()

        if language := LanguageMapping.get(filtered_tag):
            return language

    return BeatmapLanguage.Unspecified

def detect_genre_from_tags(tags: List[str]) -> BeatmapGenre:
    for tag in tags:
        filtered_tag = tag.lower().strip(",").strip()

        if genre := GenreMapping.get(filtered_tag):
            return genre

    return BeatmapGenre.Unspecified

def detect_explicit_from_tags(tags: List[str]) -> bool:
    for tag in tags:
        filtered_tag = tag.lower().strip(",").strip()

        if filtered_tag == "explicit":
            return True

    return False

def next_beatmapset_id(session: Session) -> int:
    """Get the next availabe beatmapset id"""
    while True:
        database_id = session.query(
            func.nextval('beatmapsets_id_seq')
        ).scalar()

        exists = session.query(DBBeatmapset.id) \
            .filter(DBBeatmapset.id == database_id) \
            .count() > 0

        if exists:
            continue

        return database_id

def next_beatmap_id(session: Session) -> int:
    """Get the next availabe beatmap id"""
    while True:
        database_id = session.query(
            func.nextval('beatmaps_id_seq')
        ).scalar()

        exists = session.query(DBBeatmap.id) \
            .filter(DBBeatmap.id == database_id) \
            .count() > 0

        if exists:
            continue

        return database_id
