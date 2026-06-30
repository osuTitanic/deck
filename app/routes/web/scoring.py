
from starlette.datastructures import (
    QueryParams,
    UploadFile,
    FormData
)
from fastapi import (
    HTTPException,
    APIRouter,
    Request,
    Depends,
    Query,
    Form
)

from py3rijndael import RijndaelCbc, Pkcs7Padding
from datetime import datetime, timedelta
from concurrent.futures import Future
from sqlalchemy.orm import Session
from typing import Tuple, List
from copy import copy

from app.helpers import achievements as AchievementManager
from app.helpers.score import Score, ScoreStatus
from app.helpers.enums import BadFlags
from app.helpers.chart import Chart
from app.helpers import highlights, replays

from app.common.constants import GameMode, ButtonState, NotificationType, Mods
from app.common.helpers.ip import resolve_ip_address_fastapi
from app.common.helpers.score import calculate_rx_score
from app.common.database import DBStats, DBScore, DBUser
from app.common.config import config_instance as config
from app.common.cache import leaderboards, status
from app.common.helpers import performance
from app.common.constants import regexes
from app.common import officer
from app import utils

from app.common.database.repositories import (
    notifications,
    achievements,
    histories,
    beatmaps,
    scores,
    logins,
    plays,
    users,
    stats
)

import hashlib
import base64
import app

router = APIRouter()

def decrypt_string(
    b64: str | None,
    iv: bytes,
    key: str = "h89f2-890h2h89b34g-h80g134n90133"
) -> str | None:
    """Decrypt a rinjdael encrypted string"""
    if b64 is None:
        return None

    rjn = RijndaelCbc(
        key=key.encode(),
        iv=iv,
        padding=Pkcs7Padding(32),
        block_size=32
    )
    return rjn.decrypt(base64.b64decode(b64)).decode()

async def parse_score_data(request: Request) -> Score:
    """Parse the score submission request and return a score object"""
    user_agent = request.headers.get('user-agent', 'osu!')
    ip = resolve_ip_address_fastapi(request)

    if not regexes.OSU_USER_AGENT.match(user_agent):
        officer.call(f'Invalid user agent on score submission: "{user_agent}" ({ip})')
        raise HTTPException(400)

    query = request.query_params
    form = await request.form()

    if score_data := query.get('score'):
        # Legacy score was submitted via. query argument
        return await parse_legacy_score_data(
            score_data, query, form, ip
        )

    # NOTE: The form data can contain two "score" sections, where one
    #       of them is the score data, and the other is the replay

    if not (score_form := form.getlist('score')):
        officer.call(f'Got score submission without score data! ({ip})')
        raise HTTPException(400)

    score_data = score_form[0]
    fun_spoiler = form.get('fs')
    client_hash = form.get('s')
    processes = form.get('pl')
    failtime = form.get('ft')
    exited = form.get('x')

    # Ensure form data is of the correct type
    if not isinstance(score_data, str):
        officer.call(f'Invalid score data type on score submission: "{type(score_data)}" ({ip})')
        raise HTTPException(400)

    if fun_spoiler is not None and not isinstance(fun_spoiler, str):
        officer.call(f'Invalid fun spoiler type on score submission: "{type(fun_spoiler)}" ({ip})')
        raise HTTPException(400)

    if client_hash is not None and not isinstance(client_hash, str):
        officer.call(f'Invalid client hash type on score submission: "{type(client_hash)}" ({ip})')
        raise HTTPException(400)

    if processes is not None and not isinstance(processes, str):
        officer.call(f'Invalid processes type on score submission: "{type(processes)}" ({ip})')
        raise HTTPException(400)

    replay_data: bytes | None = None

    if len(score_form) > 1:
        # Replay data was provided
        replay = score_form[-1]

        if not replay:
            officer.call(f'Got score submission with empty replay data! ({ip})')
            raise HTTPException(400)

        if not isinstance(replay, UploadFile):
            officer.call(f'Invalid replay type on score submission: "{type(replay)}" ({ip})')
            raise HTTPException(400)

        if replay.filename not in ('replay', 'score'):
            officer.call(f'Invalid replay name on score submission: "{replay.filename}" ({ip})')
            raise HTTPException(400)

        if replay.size and replay.size > 10 * 1024 * 1024: # 10 MB
            officer.call(f'Replay file too large: {replay.size} bytes ({ip})')
            raise HTTPException(400)

        replay_data = await replay.read()

    # Default decryption key for old score submission endpoints
    decryption_key = "h89f2-890h2h89b34g-h80g134n90133"

    if osu_version := form.get('osuver'):
        # New score submission endpoint uses a different encryption key
        decryption_key = f"osu!-scoreburgr---------{osu_version}"

    if iv := form.get('iv'):
        # Score data is encrypted
        try:
            assert isinstance(iv, str), "IV must be a string"
            iv = base64.b64decode(iv)
            client_hash = decrypt_string(client_hash, iv, decryption_key)
            fun_spoiler = decrypt_string(fun_spoiler, iv, decryption_key)
            score_data = decrypt_string(score_data, iv, decryption_key)
            processes = decrypt_string(processes, iv, decryption_key)
        except Exception as e:
            # Most likely an invalid score encryption key
            officer.call(
                f'Failed to decrypt score data: {e} ({ip})',
                exc_info=e
            )
            raise HTTPException(400)

    try:
        score = Score.parse(
            score_data,
            replay_data,
            bool(exited) if exited else None,
            int(failtime) if failtime else None
        )
    except Exception as e:
        officer.call(
            f'Failed to parse score data: {e} ({ip})',
            exc_info=e
        )
        raise HTTPException(400)

    score.is_legacy = request.url.path != '/web/osu-submit-modular-selector.php'
    score.fun_spoiler = fun_spoiler
    score.client_hash = client_hash
    score.processes = processes
    return score

async def parse_legacy_score_data(
    score_data: str,
    query: QueryParams,
    form: FormData,
    ip: str
) -> Score:
    failtime: str | None = query.get('ft', '0')
    exited: str | None = query.get('x', None)

    replay: bytes | None = None
    replay_file = form.get('score')

    if replay_file is not None:
        if not isinstance(replay_file, UploadFile):
            officer.call(f'Invalid replay type on score submission: "{type(replay_file)}" ({ip})')
            raise HTTPException(400)

        if replay_file.filename != 'replay':
            officer.call(f'Invalid replay name on score submission: "{replay_file.filename}" ({ip})')
            raise HTTPException(400)

        if replay_file.size and replay_file.size > 10 * 1024 * 1024: # 10 MB
            officer.call(f'Replay file too large: {replay_file.size} bytes ({ip})')
            raise HTTPException(400)

        replay = await replay_file.read()

    try:
        return Score.parse(
            score_data,
            replay,
            bool(exited),
            int(failtime)
        )
    except Exception as e:
        officer.call(
            f'Failed to parse score data: {e} ({ip})',
            exc_info=e
        )
        raise HTTPException(400)

def perform_score_validation(
    score: Score,
    player: DBUser,
    session: Session
) -> str | None:
    """Validate the score submission requests and return an error if the validation fails"""
    app.session.logger.debug('Performing score validation...')

    if (
        score.total_objects <= 0 or
        score.total_score <= 0 or
        score.max_combo <= 0
    ):
        officer.call(
            f'"{score.username}" submitted score with no hits, score or combo.'
        )
        return 'error: no'

    if score.beatmap.mode > 0 and score.mode == GameMode.Osu:
        # Player was playing osu!std on a beatmap with mode taiko, fruits or mania
        # This can happen in old clients, where these modes were not implemented
        return 'error: no'

    if score.mode == GameMode.CatchTheBeat and score.version <= 504:
        # b504 and below let you specify the size of the catcher by changing
        # the skin, resulting in unfair advantages when using very wide ones:
        # https://ibb.co/mrWyc2RR -> https://ibb.co/3yjXJcbm
        return 'error: no'

    unranked_mods = (
        Mods.Autoplay,
        Mods.Cinema,
        Mods.Target,
        Mods.ScoreV2,
        Mods.Random,
        Mods.KeyCoop,
        Mods.Key1,
        Mods.Key2,
        Mods.Key3,
    )

    if any(mod in score.enabled_mods for mod in unranked_mods):
        officer.call(
            f'"{score.username}" submitted score with unranked mods: {score.enabled_mods.name}.'
        )
        return 'error: no'

    client_hash = status.client_hash(player.id)

    if (
        score.client_hash is not None
        and client_hash is not None
        and not client_hash.startswith(score.client_hash)
    ):
        officer.call(
            f'"{score.username}" submitted score with client hash mismatch. '
            f'({score.client_hash} -> {client_hash})'
        )
        return 'error: no'

    if score.passed:
        # Replay must exist when the score is a pass
        if not score.replay:
            officer.call(
                f'"{score.username}" submitted score without replay.'
            )
            app.session.events.submit(
                'restrict',
                user_id=player.id,
                autoban=True,
                reason='Score submission without replay'
            )
            return 'error: ban'

        # Check for duplicate score
        replay_hash = hashlib.md5(score.replay).hexdigest()
        duplicate_score = scores.fetch_by_replay_checksum(replay_hash, session)

        if duplicate_score:
            if duplicate_score.user_id != player.id:
                officer.call(
                    f'"{score.username}" submitted duplicate replay in score submission '
                    f'({duplicate_score.replay_md5}).'
                )
                app.session.events.submit(
                    'restrict',
                    user_id=player.id,
                    autoban=True,
                    reason='Duplicate replay in score submission'
                )
                return 'error: ban'

            app.session.logger.warning(
                f'"{score.username}" submitted duplicate replay from themselves '
                f'({duplicate_score.replay_md5}).'
            )
            return 'error: no'

        flags = [
            BadFlags.FlashLightImageHack,
            BadFlags.SpinnerHack,
            BadFlags.TransparentWindow,
            BadFlags.FastPress,
            BadFlags.FlashlightChecksumIncorrect,
            BadFlags.ChecksumFailure,
            BadFlags.RawMouseDiscrepancy,
            BadFlags.RawKeyboardDiscrepancy
        ]

        if any(flag in score.flags for flag in flags):
            officer.call(
                f'"{score.username}" submitted score with bad flags: {score.flags.name}.',
                file=(score.replay_filename, score.serialize_replay())
            )

        if not replays.validate(score.replay):
            officer.call(
                f'"{score.username}" submitted score with invalid replay.',
                file=(score.replay_filename, score.serialize_replay())
            )
            return 'error: no'

    if score.check_invalid_mods():
        officer.call(
            f'"{score.username}" submitted score with invalid mods: {score.enabled_mods.name}.',
            file=(score.replay_filename, score.serialize_replay())
        )

        if not player.is_verified:
            app.session.events.submit(
                'restrict',
                user_id=player.id,
                autoban=True,
                reason='Invalid mods on score submission'
            )
            return 'error: ban'

    account_age = (datetime.now() - player.created_at)
    pp_cutoff = min(1500, max(750, account_age.total_seconds() / 8))

    if score.beatmap.awards_pp and score.pp >= pp_cutoff:
        officer.call(
            f'"{score.username}" exceeded the pp limit ({score.pp}).',
            file=(score.replay_filename, score.serialize_replay())
        )

        if not player.is_verified:
            app.session.events.submit(
                'restrict',
                user_id=player.id,
                autoban=True,
                reason=f'Exceeded pp limit ({round(score.pp)})'
            )
            return 'error: ban'

def upload_replay(score: Score, score_id: int) -> None:
    if not score.passed or not score.replay:
        return

    if score.status_pp <= ScoreStatus.Exited:
        return

    app.session.logger.debug('Uploading replay...')

    # Check replay size (10mb max)
    if len(score.replay) > 1e+7:
        app.session.logger.warning('Replay size exceeded maximum limit.')
        return

    score_rank = scores.fetch_score_index_by_id(
        mods=score.enabled_mods.value,
        beatmap_id=score.beatmap.id,
        mode=score.mode.value,
        score_id=score_id
    )

    # Replay will always be cached temporarily
    app.session.storage.cache_replay(
        score_id,
        score.replay
    )

    if not score.beatmap.is_ranked:
        return

    if score.status_pp < ScoreStatus.Submitted:
        return

    if score_rank > config.SCORE_RESPONSE_LIMIT * 10:
        return

    # Replay met the requirement to be uploaded permanently
    return app.session.storage.upload_replay(
        score_id,
        score.replay
    )

def calculate_weighted_pp(scores: List[DBScore]) -> float:
    """Calculate the weighted pp for a list of scores"""
    if not scores:
        return 0

    weighted_pp = sum(score.pp * 0.95**index for index, score in enumerate(scores))
    bonus_pp = 416.6667 * (1 - 0.9994 ** len(scores))
    return weighted_pp + bonus_pp

def calculate_weighted_acc(scores: List[DBScore]) -> float:
    """Calculate the weighted acc for a list of scores"""
    if not scores:
        return 0

    weighted_acc = sum(score.acc * 0.95**index for index, score in enumerate(scores))
    bonus_acc = 100.0 / (20 * (1 - 0.95 ** len(scores)))
    return (weighted_acc * bonus_acc) / 100

def update_stats(
    score: Score,
    player: DBUser,
    session: Session
) -> Tuple[DBStats, DBStats, dict]:
    """Update the users and beatmaps stats. It will return the old & new stats for the user"""
    app.session.logger.debug('Updating user stats...')

    # Update beatmap stats
    score.beatmap.playcount += 1
    score.beatmap.passcount += 1 if score.passed else 0
    session.flush()

    # Update user stats
    user_stats = stats.fetch_by_mode(
        score.user.id,
        score.mode.value,
        session
    )

    old_stats = copy(user_stats)
    old_rank, old_pp = resolve_preferred_ranking(player, score.mode.value)
    new_rank, new_pp = old_rank, old_pp

    user_stats.playcount += 1
    user_stats.playtime += score.elapsed_time
    user_stats.tscore += score.total_score
    user_stats.total_hits += score.total_hits
    session.flush()

    histories.update_plays(
        user_stats.user_id,
        user_stats.mode,
        session
    )

    plays.update(
        score.beatmap.filename,
        score.beatmap.id,
        score.user.id,
        score.beatmap.set_id,
        session=session
    )

    best_scores_by_score = scores.fetch_best_by_score(
        user_id=score.user.id,
        mode=score.mode.value,
        session=session
    )

    best_scores = scores.fetch_best(
        user_id=score.user.id,
        mode=score.mode.value,
        exclude_approved=(not config.APPROVED_MAP_REWARDS),
        session=session
    )

    # Update max combo, if higher
    if score.beatmap.is_ranked and score.has_pb:
        if score.max_combo > user_stats.max_combo:
            user_stats.max_combo = score.max_combo

    if best_scores:
        # Update pp & acc
        user_stats.pp = calculate_weighted_pp(best_scores)
        user_stats.acc = calculate_weighted_acc(best_scores)

        # Update rscore
        user_stats.rscore = sum(
            score.total_score
            for score in best_scores_by_score
        )

        # Update ppv1, if config allows for it
        if not config.FROZEN_PPV1_UPDATES:
            user_stats.ppv1 = performance.calculate_weighted_ppv1(best_scores)

        # Update score grades
        grades = scores.fetch_grades(
            user_stats.user_id,
            user_stats.mode,
            session=session
        )

        stats.update(
            user_stats.user_id,
            user_stats.mode,
            {
                f'{grade.lower()}_count': count
                for grade, count in grades.items()
            },
            session=session
        )

        leaderboards.update(
            user_stats,
            player.country.lower()
        )

        user_stats.rank = leaderboards.global_rank(
            user_stats.user_id,
            user_stats.mode
        )

        if not config.FROZEN_RANK_UPDATES:
            histories.update_rank(
                user_stats,
                player.country
            )

        session.flush()

        new_rank, new_pp = resolve_preferred_ranking(
            player,
            score.mode.value
        )

    return (
        user_stats,
        old_stats,
        {
            "old_rank": old_rank,
            "old_pp": old_pp,
            "new_rank": new_rank,
            "new_pp": new_pp
        }
    )

def unlock_achievements(
    score: Score,
    score_object: DBScore,
    player: DBUser,
    session: Session
) -> List[str]:
    app.session.logger.debug('Checking achievements...')

    unlocked_achievements = achievements.fetch_many(player.id, session)
    ignore_list = [a.filename for a in unlocked_achievements]

    new_achievements = AchievementManager.check(score_object, session, ignore_list)
    achievement_response = [a.filename for a in new_achievements]

    if new_achievements:
        achievements.create_many(
            new_achievements,
            player.id,
            session
        )

        # Send notification
        if len(new_achievements) > 1:
            names = [f'"{a.name}"' for a in new_achievements]
            achievement_names = ', '.join(name for name in names[:-1])
            notification_header = 'Achievements Unlocked!'
            notification_message = (
                'Congratulations for unlocking the '
                f'{achievement_names} and {names[-1]} achievements!'
            )

        else:
            notification_header = 'Achievement Unlocked!'
            notification_message = (
                'Congratulations for unlocking the '
                f'"{new_achievements[0].name}" achievement!'
            )

        notifications.create(
            player.id,
            NotificationType.Achievement.value,
            notification_header,
            notification_message,
            link=f'{config.OSU_BASEURL}/u/{player.id}#achievements',
            session=session
        )

    return achievement_response

def resolve_preferred_ranking(user: DBUser, mode: int) -> Tuple[int, int]:
    """Receive the preferred ranking type from cache (ppv2/ppv1/tscore/...)"""
    ranking_mapping = {
        'global': leaderboards.global_rank,
        'rscore': leaderboards.score_rank,
        'tscore': leaderboards.total_score_rank,
        'clears': leaderboards.clears_rank,
        'ppv1': leaderboards.ppv1_rank
    }

    preferred_rank_function = ranking_mapping.get(
        user.preferred_ranking,
        leaderboards.global_rank
    )

    preferred_rank = preferred_rank_function(
        user.id,
        mode
    )

    if user.preferred_ranking != 'ppv1':
        return (
            preferred_rank,
            leaderboards.performance(user.id, mode)
        )

    return (
        preferred_rank,
        leaderboards.ppv1(user.id, mode)
    )

def response_charts(
    score: Score,
    score_id: int,
    ranking: dict,
    old_stats: DBStats,
    new_stats: DBStats,
    old_rank: int,
    new_rank: int,
    achievement_response: List[str],
    session: Session
) -> List[Chart]:
    """Generates the required charts for a score submission response"""
    beatmap_info = Chart()
    beatmap_info['beatmapId'] = score.beatmap.id
    beatmap_info['beatmapSetId'] = score.beatmap.set_id
    beatmap_info['beatmapPlaycount'] = score.beatmap.playcount
    beatmap_info['beatmapPasscount'] = score.beatmap.passcount
    beatmap_info['approvedDate'] = score.beatmap.beatmapset.approved_at

    # TODO: Implement monthly charts

    overall_chart = Chart()
    overall_chart['chartId'] = 'overall'
    overall_chart['chartName'] = 'Overall Ranking'
    overall_chart['chartUrl'] = f'{config.OSU_BASEURL}/p/playerranking/?f={score.user.name}'
    overall_chart['chartEndDate'] = ''
    overall_chart['achievements'] = ' '.join(achievement_response)
    overall_chart['achievements-new'] = '' # TODO

    overall_chart.entry('rank', ranking["old_rank"], ranking["new_rank"])
    overall_chart.entry('rankedScore', old_stats.rscore, round(new_stats.rscore))
    overall_chart.entry('totalScore', old_stats.tscore, round(new_stats.tscore))
    overall_chart.entry('playCount', old_stats.playcount, new_stats.playcount)
    overall_chart.entry('maxCombo', old_stats.max_combo, new_stats.max_combo)
    overall_chart.entry('pp', round(ranking["old_pp"]), round(ranking["new_pp"]))
    overall_chart.entry(
        'accuracy',
        round(old_stats.acc, 4) * (100 if not score.is_legacy else 1),
        round(new_stats.acc, 4) * (100 if not score.is_legacy else 1)
    )

    overall_chart['onlineScoreId'] = score_id
    overall_chart['toNextRankUser'] = ''
    overall_chart['toNextRank'] = '0'

    if score.beatmap.is_ranked:
        overall_chart.entry(
            'beatmapRanking',
            old_rank,
            new_rank
        )

        difference, next_user = leaderboards.player_above(
            score.user.id,
            score.mode.value
        )

        if difference > 0:
            overall_chart['toNextRankUser'] = next_user
            overall_chart['toNextRank'] = difference

    if score.is_legacy:
        return [beatmap_info, overall_chart]

    beatmap_ranking = Chart()
    beatmap_ranking['chartId'] = 'beatmap'
    beatmap_ranking['chartName'] = 'Beatmap Ranking'
    beatmap_ranking['chartUrl'] = f'{config.OSU_BASEURL}/b/{score.beatmap.id}'

    old_score = score.personal_best_score
    new_score = score.to_database()

    if old_score:
        beatmap_ranking.entry('rank', old_rank, new_rank)
        beatmap_ranking.entry('rankedScore', old_score.total_score, new_score.total_score)
        beatmap_ranking.entry('totalScore', old_score.total_score, new_score.total_score)
        beatmap_ranking.entry('maxCombo', old_score.max_combo, new_score.max_combo)
        beatmap_ranking.entry('accuracy', round(old_score.acc, 4) * 100, round(new_score.acc, 4) * 100)
        beatmap_ranking.entry('pp', round(old_score.pp), round(new_score.pp))
    else:
        beatmap_ranking.entry('rank', None, new_rank)
        beatmap_ranking.entry('rankedScore', None, new_score.total_score)
        beatmap_ranking.entry('totalScore', None, new_score.total_score)
        beatmap_ranking.entry('maxCombo', None, new_score.max_combo)
        beatmap_ranking.entry('accuracy', None, round(new_score.acc, 4) * 100)
        beatmap_ranking.entry('pp', None, round(new_score.pp))

    score_above = scores.fetch_score_above(
        score.beatmap.id,
        score.mode.value,
        score.total_score,
        session=session
    )

    beatmap_ranking['toNextRank'] = '0'
    beatmap_ranking['toNextRankUser'] = ''

    if score_above:
        beatmap_ranking['toNextRankUser'] = score_above.user.name
        beatmap_ranking['toNextRank'] = score_above.total_score - score.total_score

    return [beatmap_info, beatmap_ranking, overall_chart]

def thread_callback(future: Future) -> None:
    if not (e := future.exception()):
        return

    officer.call(
        f'Failed to execute score submission task.',
        exc_info=e
    )

@router.post("/osu-submit-modular-selector.php")
@router.post('/osu-submit-modular.php')
def score_submission(
    request: Request,
    # This will get sent when the "FlashLightImageHack" flag is triggered
    # We don't need to use it, since the flag will already restrict them
    flashlight_screenshot: bytes | None = Form(None, alias='i'),
    legacy_password: str | None = Query(None, alias='pass'),
    password: str | None = Form(None, alias='pass'),
    score: Score = Depends(parse_score_data),
    session: Session = Depends(app.session.database.yield_session),
) -> str:
    password = legacy_password or password

    score.user = users.fetch_by_name(
        score.username,
        session
    )

    if not (player := score.user):
        app.session.logger.warning(f'Failed to submit score: Invalid User')
        return 'error: nouser'

    if not utils.check_password(password, player.bcrypt):
        app.session.logger.warning(f'Failed to submit score: Invalid Password')
        return 'error: pass'

    if not player.activated:
        app.session.logger.warning(f'Failed to submit score: Inactive')
        return 'error: inactive'

    if player.restricted:
        app.session.logger.warning(f'Failed to submit score: Restricted')
        return 'error: ban'

    if player.is_bot:
        app.session.logger.warning(f'Failed to submit score: Bot account')
        return 'error: no'

    score.beatmap = beatmaps.fetch_by_checksum(
        score.file_checksum,
        session
    )

    if not score.beatmap:
        app.session.logger.warning(f'Failed to submit score: Beatmap not found')
        return 'error: beatmap'

    if not status.exists(player.id):
        # Bancho may be down most likely
        # Let the client resend the request
        raise HTTPException(503)

    if score.user.stats:
        score.user.stats.sort(
            key=lambda x: x.mode
        )

    if score.client_hash:
        score.client_hash = (
            score.client_hash.removesuffix(':')
        )

    users.update(
        player.id,
        {'latest_activity': datetime.now()},
        session
    )

    if score.version <= 0:
        # Client didn't provide a version
        # Try to get it from bancho instead
        score.version = status.version(player.id) or 0

    # Fetch current osu! client version
    score.version_string = (
        logins.fetch_last_osu_version(player.id, session)
        or f"b{score.version}"
    )

    score.pp = score.calculate_ppv2()
    score.ppv1 = score.calculate_ppv1(session)

    if (error := perform_score_validation(score, player, session)) != None:
        session.rollback()
        return error

    if score.relaxing:
        # Recalculate rx total score
        score.total_score = calculate_rx_score(
            score.to_database(),
            score.beatmap
        )

    if score.beatmap.is_ranked:
        score.personal_best_pp = scores.fetch_personal_best(
            score.beatmap.id,
            score.user.id,
            score.mode.value,
            session=session
        )

        score.personal_best_score = scores.fetch_personal_best_score(
            score.beatmap.id,
            score.user.id,
            score.mode.value,
            session=session
        )

        score.status_pp = score.calculate_pp_status(session)
        score.status_score = score.calculate_score_status(session)

        # Get old rank before submitting score
        old_rank = scores.fetch_score_index_by_id(
                score.personal_best_score.id,
                score.beatmap.id,
                mode=score.mode.value,
                session=session
            ) \
            if score.personal_best_score else 0

        # Submit to database
        score_object = score.to_database()
        score_object.client_hash = score.client_hash

        if not config.ALLOW_RELAX and score.relaxing:
            score_object.hidden = True

        session.add(score_object)
        session.commit()

        # Try to upload replay
        app.session.score_executor.submit(
            upload_replay,
            score,
            score_object.id
        ).add_done_callback(thread_callback)

    new_stats, old_stats, ranking = update_stats(score, player, session)

    # Commit all changes to the database
    session.commit()

    # Reload stats on bancho
    app.session.events.submit(
        'user_update',
        user_id=player.id,
        mode=score.mode.value
    )

    if not score.beatmap.is_ranked:
        return 'error: beatmap'

    if not config.ALLOW_RELAX and score.relaxing:
        return 'error: no'

    achievement_response: List[str] = []

    if score.passed and not score.relaxing:
        achievement_response = unlock_achievements(
            score,
            score_object,
            player,
            session
        )

    new_rank = scores.fetch_score_index_by_tscore(
        score_object.total_score,
        score.beatmap.id,
        mode=score.mode.value,
        session=session
    )

    response = response_charts(
        score,
        score_object.id,
        ranking,
        old_stats,
        new_stats,
        old_rank,
        new_rank,
        achievement_response,
        session
    )

    app.session.logger.info(
        f'"{score.username}" submitted {"failed " if score.failtime else ""}score on {score.beatmap.full_name}'
        f' ({config.OSU_BASEURL}/scores/{score_object.id})'
    )

    session.commit()

    # Send highlights on #announce
    if score.passed:
        app.session.score_executor.submit(
            highlights.check,
            score_object.id, score.user,
            new_stats, old_stats,
            new_rank, old_rank
        ).add_done_callback(thread_callback)

    return "\n".join([chart.get() for chart in response])

@router.post('/osu-submit.php')
@router.post('/osu-submit-new.php')
def legacy_score_submission(
    request: Request,
    password: str | None = Query(None, alias='pass'),
    score: Score = Depends(parse_score_data),
    session: Session = Depends(app.session.database.yield_session),
) -> str:
    score.user = users.fetch_by_name(
        score.username,
        session
    )

    if not (player := score.user):
        app.session.logger.warning(f'Failed to submit score: Invalid User')
        raise HTTPException(401)

    if not utils.check_password(password, player.bcrypt):
        app.session.logger.warning(f'Failed to submit score: Invalid Password')
        raise HTTPException(401)

    if not player.activated:
        app.session.logger.warning(f'Failed to submit score: Inactive')
        raise HTTPException(401)

    if player.restricted:
        app.session.logger.warning(f'Failed to submit score: Restricted')
        raise HTTPException(401)

    if player.is_bot:
        app.session.logger.warning(f'Failed to submit score: Bot account')
        return ""

    score.beatmap = beatmaps.fetch_by_checksum(
        score.file_checksum,
        session
    )

    if not score.beatmap:
        app.session.logger.warning(f'Failed to submit score: Beatmap not found')
        raise HTTPException(404)

    if not status.exists(player.id):
        # Bancho may be down most likely
        # Let the client resend the request
        raise HTTPException(503)

    if score.user.stats:
        score.user.stats.sort(
            key=lambda x: x.mode
        )

    if score.client_hash:
        score.client_hash = (
            score.client_hash.removesuffix(':')
        )

    users.update(
        player.id,
        {'latest_activity': datetime.now()},
        session
    )

    if score.version <= 0:
        # Client didn't provide a version
        # Try to get it from bancho instead
        score.version = status.version(player.id) or 0

    # Fetch current osu! client version
    score.version_string = (
        logins.fetch_last_osu_version(player.id, session)
        or f"b{score.version}"
    )

    score.pp = score.calculate_ppv2()
    score.ppv1 = score.calculate_ppv1(session)

    if (error := perform_score_validation(score, player, session)) != None:
        raise HTTPException(400, detail=error)

    if score.relaxing:
        # Recalculate rx total score
        score.total_score = calculate_rx_score(
            score.to_database(),
            score.beatmap
        )

    if score.version < 452 and Mods.Nightcore in score.enabled_mods:
        # Prevent "Taiko" mod plays from being submitted
        raise HTTPException(400)

    if score.beatmap.is_ranked:
        score.personal_best_pp = scores.fetch_personal_best(
            score.beatmap.id,
            score.user.id,
            score.mode.value,
            session=session
        )

        score.personal_best_score = scores.fetch_personal_best_score(
            score.beatmap.id,
            score.user.id,
            score.mode.value,
            session=session
        )

        score.status_pp = score.calculate_pp_status(session)
        score.status_score = score.calculate_score_status(session)

        # Get old rank before submitting score
        old_rank = scores.fetch_score_index_by_id(
                score.personal_best_score.id,
                score.beatmap.id,
                mode=score.mode.value,
                session=session
            ) \
            if score.personal_best_score else 0

        # Submit to database
        score_object = score.to_database()

        if not config.ALLOW_RELAX and score.relaxing:
            score_object.hidden = True

        session.add(score_object)
        session.commit()

        # Try to upload replay
        app.session.score_executor.submit(
            upload_replay,
            score,
            score_object.id
        ).add_done_callback(thread_callback)

    new_stats, old_stats, ranking = update_stats(score, player, session)

    # Commit all changes to the database
    session.commit()

    # Reload stats on bancho
    app.session.events.submit(
        'user_update',
        user_id=player.id,
        mode=score.mode.value
    )

    if not score.beatmap.is_ranked:
        return ""

    if not config.ALLOW_RELAX and score.relaxing:
        return ""

    app.session.logger.info(
        f'"{score.username}" submitted {"failed " if score.failtime else ""}score on {score.beatmap.full_name}'
        f' ({config.OSU_BASEURL}/scores/{score_object.id})'
    )

    if not score.passed:
        return ""

    achievement_response: List[str] = []
    response: List[Chart] = []

    if not score.relaxing:
        achievement_response = unlock_achievements(
            score,
            score_object,
            player,
            session
        )

    beatmap_rank = scores.fetch_score_index_by_id(
        score_object.id,
        score.beatmap.id,
        mode=score.mode.value,
        session=session
    )

    session.commit()

    if score.is_score_pb:
        response.append(str(beatmap_rank))
    else:
        response.append('0')

    difference, next_user = leaderboards.player_above(
        player.id,
        score.mode.value
    )
    response.append(str(round(difference)))

    if achievement_response:
        response.append(" ".join(achievement_response))

    # Send highlights on #announce
    if score.passed:
        app.session.score_executor.submit(
            highlights.check,
            score_object.id, score.user,
            new_stats, old_stats,
            beatmap_rank, old_rank
        ).add_done_callback(thread_callback)

    return "\n".join(response)
