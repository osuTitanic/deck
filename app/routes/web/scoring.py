
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
from typing import Optional, Tuple, List
from copy import copy

from app.common.constants import GameMode, BadFlags, ButtonState, NotificationType, Mods
from app.common.helpers.ip import resolve_ip_address_fastapi
from app.common.helpers.score import calculate_rx_score
from app.common.database import DBStats, DBScore, DBUser
from app import achievements as AchievementManager
from app.objects import Score, ScoreStatus, Chart
from app.common.cache import leaderboards, status
from app.common.helpers import performance
from app.common.constants import regexes
from app.common import officer

from app.common.database.repositories import (
    notifications,
    achievements,
    histories,
    beatmaps,
    scores,
    plays,
    users,
    stats
)

import hashlib
import base64
import config
import utils
import lzma
import app

router = APIRouter()

def decrypt_string(
    b64: str | None,
    iv: bytes,
    key: str = config.SCORE_SUBMISSION_KEY
) -> str | None:
    """Decrypt a rinjdael encrypted string"""
    if not b64:
        return

    rjn = RijndaelCbc(
        key=key,
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
        # Legacy score was submitted
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
    replay = None

    if len(score_form) > 1:
        # Replay data was provided
        replay = score_form[-1]

        if not replay:
            officer.call(f'Got score submission with empty replay data! ({ip})')
            raise HTTPException(400)

        if replay.filename not in ('replay', 'score'):
            officer.call(f'Invalid replay name on score submission: "{replay.filename}" ({ip})')
            raise HTTPException(400)

        replay = await replay.read()

    decryption_key = config.SCORE_SUBMISSION_KEY

    if osu_version := form.get('osuver'):
        # New score submission endpoint uses a different encryption key
        decryption_key = f"osu!-scoreburgr---------{osu_version}"

    if iv := form.get('iv'):
        # Score data is encrypted
        try:
            iv = base64.b64decode(iv)
            client_hash = decrypt_string(client_hash, iv, decryption_key)
            fun_spoiler = decrypt_string(fun_spoiler, iv, decryption_key)
            score_data = decrypt_string(score_data, iv, decryption_key)
            processes = decrypt_string(processes, iv, decryption_key)
        except (UnicodeDecodeError, TypeError) as e:
            # Most likely an invalid score encryption key
            officer.call(
                f'Could not decrypt score data: {e} ({ip})',
                exc_info=e
            )
            raise HTTPException(400)

    try:
        score = Score.parse(
            score_data,
            replay,
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
    query: dict,
    form: dict,
    ip: str
) -> Score:
    failtime: Optional[str] = query.get('ft', 0)
    exited: Optional[str] = query.get('x', False)
    replay: Optional[bytes] = None
    replay_file = form.get('score')

    if replay_file and replay_file.filename != 'replay':
        officer.call(f'Invalid replay name on score submission: "{replay.filename}" ({ip})')
        raise HTTPException(400)

    if replay_file:
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

def validate_replay(replay_bytes: bytes) -> bool:
    """Validate the replay contents"""
    app.session.logger.debug('Validating replay...')

    try:
        replay = lzma.decompress(replay_bytes).decode()
        frames = replay.split(',')

        if len(frames) < 100:
            # Hopefully this doesn't lead to false-positivies
            officer.call(
                f'Replay validation failed: Not enough replay frames ({len(frames)})'
            )
            return False

        for frame in frames:
            if not frame:
                continue

            frame_data = frame.split('|')

            if len(frame_data) != 4:
                officer.call(
                    f'Replay validation failed: Invalid frame data ({frame_data})'
                )
                return False

            if frame_data[0] == "-12345":
                seed = int(frame_data[3])
                continue

            time = int(frame_data[0])
            x = float(frame_data[1])
            y = float(frame_data[2])
            button_state = ButtonState(int(frame_data[3]))
    except Exception as e:
        officer.call(
            f'Replay validation failed: {e}',
            exc_info=e
        )
        return False

    return True

def perform_score_validation(score: Score, player: DBUser) -> Optional[str]:
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
    
    unranked_mods = (
        Mods.Autoplay,
        Mods.Cinema,
        Mods.Target
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
        # Check for replay
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
        duplicate_score = scores.fetch_by_replay_checksum(replay_hash, score.session)

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

    if score.check_invalid_mods():
        officer.call(
            f'"{score.username}" submitted score with invalid mods.'
        )

        if not player.is_verified:
            app.session.events.submit(
                'restrict',
                user_id=player.id,
                autoban=True,
                reason='Invalid mods on score submission'
            )
            return 'error: ban'

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
            f'"{score.username}" submitted score with bad flags: {score.flags.name}. '
            f'Please review this case as soon as possible. ({replay_hash})'
        )

    if score.replay and not validate_replay(score.replay):
        officer.call(
            f'"{score.username}" submitted score with invalid replay.'
        )

        if not player.is_verified:
            app.session.events.submit(
                'restrict',
                user_id=player.id,
                autoban=True,
                reason='Invalid replay'
            )
            return 'error: ban'

    account_age = (datetime.now() - player.created_at)
    pp_cutoff = min(1500, max(750, account_age.total_seconds() / 8))

    if score.pp >= pp_cutoff:
        officer.call(
            f'"{score.username}" exceeded the pp limit ({score.pp}).'
        )

        if not player.is_verified:
            app.session.events.submit(
                'restrict',
                user_id=player.id,
                autoban=True,
                reason=f'Exceeded pp limit ({round(score.pp)})'
            )
            return 'error: ban'

    multiaccounting_lock = app.session.redis.get(f'multiaccounting:{player.id}')

    if multiaccounting_lock != None and int(multiaccounting_lock) > 0:
        officer.call(
            f'"{score.username}" submitted a score while multiaccounting.'
        )

        if not player.is_verified:
            app.session.events.submit(
                'restrict',
                user_id=player.id,
                autoban=True,
                reason='Multiaccounting'
            )
            return 'error: ban'

def upload_replay(score: Score, score_id: int) -> None:
    if score.passed and score.status_pp > ScoreStatus.Exited:
        app.session.logger.debug('Uploading replay...')

        # Check replay size (10mb max)
        if len(score.replay) > 1e+7:
            return

        score_rank = scores.fetch_score_index_by_id(
            mods=score.enabled_mods.value,
            beatmap_id=score.beatmap.id,
            mode=score.mode.value,
            score_id=score_id
        )

        # Replay will be cached temporarily and deleted after
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

        return app.session.storage.upload_replay(
            score_id,
            score.replay
        )

    # Cache replay for 30 minutes
    app.session.storage.cache_replay(
        id=score_id,
        content=score.replay,
        time=timedelta(minutes=30)
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

def update_stats(score: Score, player: DBUser) -> Tuple[DBStats, DBStats]:
    """Update the users and beatmaps stats. It will return the old & new stats for the user"""
    app.session.logger.debug('Updating user stats...')

    # Update beatmap stats
    score.beatmap.playcount += 1
    score.beatmap.passcount += 1 if score.passed else 0
    score.session.commit()

    # Update user stats
    user_stats = stats.fetch_by_mode(
        score.user.id,
        score.mode.value,
        score.session
    )

    old_stats = copy(user_stats)

    user_stats.playcount += 1
    user_stats.playtime += score.elapsed_time
    user_stats.tscore += score.total_score
    user_stats.total_hits += score.total_hits

    score.session.commit()

    histories.update_plays(
        user_stats.user_id,
        user_stats.mode,
        score.session
    )

    plays.update(
        score.beatmap.filename,
        score.beatmap.id,
        score.user.id,
        score.beatmap.set_id,
        session=score.session
    )

    best_scores_by_score = scores.fetch_best_by_score(
        user_id=score.user.id,
        mode=score.mode.value,
        session=score.session
    )

    best_scores = scores.fetch_best(
        user_id=score.user.id,
        mode=score.mode.value,
        exclude_approved=(not config.APPROVED_MAP_REWARDS),
        session=score.session
    )

    rx_scores = [score for score in best_scores if (score.mods & 128) != 0]
    ap_scores = [score for score in best_scores if (score.mods & 8192) != 0]
    vn_scores = [score for score in best_scores if (score.mods & 128) == 0 and (score.mods & 8192) == 0]

    if score.beatmap.is_ranked and score.has_pb:
        if score.max_combo > user_stats.max_combo:
            # Update max combo, if higher
            user_stats.max_combo = score.max_combo

    if best_scores:
        # Update pp
        user_stats.pp = calculate_weighted_pp(best_scores)
        user_stats.pp_vn = calculate_weighted_pp(vn_scores)
        user_stats.pp_rx = calculate_weighted_pp(rx_scores)
        user_stats.pp_ap = calculate_weighted_pp(ap_scores)

        # Update acc
        user_stats.acc = calculate_weighted_acc(best_scores)

        # Update rscore
        user_stats.rscore = sum(
            score.total_score
            for score in best_scores_by_score
        )

        # Update ppv1
        user_stats.ppv1 = performance.calculate_weighted_ppv1(best_scores)

        leaderboards.update(
            user_stats,
            player.country.lower()
        )

        user_stats.rank = leaderboards.global_rank(
            user_stats.user_id,
            user_stats.mode
        )

        histories.update_rank(
            user_stats,
            player.country
        )

        score.session.commit()

        # Update score grades
        grades = scores.fetch_grades(
            user_stats.user_id,
            user_stats.mode,
            session=score.session
        )

        stats.update(
            user_stats.user_id,
            user_stats.mode,
            {
                f'{grade.lower()}_count': count
                for grade, count in grades.items()
            },
            session=score.session
        )

    # Update preferred mode
    if player.preferred_mode != score.mode.value:
        recent_scores = scores.fetch_recent_all(
            player.id,
            limit=30,
            session=score.session
        )

        if len({s.mode for s in recent_scores}) == 1:
            users.update(
                player.id,
                {'preferred_mode': score.mode.value},
                score.session
            )

    return user_stats, old_stats

def unlock_achievements(
    score: Score,
    score_object: DBScore,
    player: DBUser,
    request: Request
) -> List[str]:
    app.session.logger.debug('Checking achievements...')

    unlocked_achievements = achievements.fetch_many(player.id, score.session)
    ignore_list = [a.filename for a in unlocked_achievements]

    new_achievements = AchievementManager.check(score_object, score.session, ignore_list)
    achievement_response = [a.filename for a in new_achievements]

    if new_achievements:
        achievements.create_many(
            new_achievements,
            player.id,
            score.session
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
            link=f'https://osu.{config.DOMAIN_NAME}/u/{player.id}#achievements'
        )

    return achievement_response

def response_charts(
    score: Score,
    score_id: int,
    old_stats: DBStats,
    new_stats: DBStats,
    old_rank: int,
    new_rank: int,
    achievement_response: List[str]
) -> List[Chart]:
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
    overall_chart['chartUrl'] = f'https://osu.{config.DOMAIN_NAME}/u/{score.user.id}'
    overall_chart['chartEndDate'] = ''
    overall_chart['achievements'] = ' '.join(achievement_response)
    overall_chart['achievements-new'] = '' # TODO

    overall_chart.entry('rank', old_stats.rank, new_stats.rank)
    overall_chart.entry('rankedScore', old_stats.rscore, new_stats.rscore)
    overall_chart.entry('totalScore', old_stats.tscore, new_stats.tscore)
    overall_chart.entry('playCount', old_stats.playcount, new_stats.playcount)
    overall_chart.entry('maxCombo', old_stats.max_combo, new_stats.max_combo)
    overall_chart.entry('pp', round(old_stats.pp), round(new_stats.pp))
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
    beatmap_ranking['chartUrl'] = f'https://osu.{config.DOMAIN_NAME}/b/{score.beatmap.id}'

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

    return [beatmap_info, beatmap_ranking, overall_chart]

@router.post("/osu-submit-modular-selector.php")
@router.post('/osu-submit-modular.php')
def score_submission(
    request: Request,
    # This will get sent when the "FlashLightImageHack" flag is triggered
    # We don't need to use it, since the flag will already restrict them
    flashlight_screenshot: Optional[bytes] = Form(None, alias='i'),
    legacy_password: Optional[str] = Query(None, alias='pass'),
    password: Optional[str] = Form(None, alias='pass'),
    score: Score = Depends(parse_score_data),
) -> str:
    password = legacy_password or password

    score.user = users.fetch_by_name(
        score.username,
        score.session
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
        return 'error: inactive'

    score.beatmap = beatmaps.fetch_by_checksum(
        score.file_checksum,
        score.session
    )

    if not score.beatmap:
        app.session.logger.warning(f'Failed to submit score: Beatmap not found')
        return 'error: beatmap'

    if not status.exists(player.id):
        # Let the client resend the request
        return ''

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
        score.session
    )

    score.pp = score.calculate_ppv2()
    score.ppv1 = score.calculate_ppv1()

    if (error := perform_score_validation(score, player)) != None:
        return error

    if score.relaxing:
        # Recalculate rx total score
        score.total_score = calculate_rx_score(
            score.to_database(),
            score.beatmap
        )

    if score.version <= 0:
        # Client didn't provide a version
        # Try to get it from bancho instead
        score.version = status.version(player.id) or 0

    if score.beatmap.is_ranked:
        score.personal_best_pp = scores.fetch_personal_best(
            score.beatmap.id,
            score.user.id,
            score.mode.value,
            session=score.session
        )

        score.personal_best_score = scores.fetch_personal_best_score(
            score.beatmap.id,
            score.user.id,
            score.mode.value,
            session=score.session
        )

        score.status_pp = score.calculate_pp_status()
        score.status_score = score.calculate_score_status()

        # Get old rank before submitting score
        old_rank = scores.fetch_score_index_by_id(
                    score.personal_best_pp.id,
                    score.beatmap.id,
                    mode=score.mode.value,
                    session=score.session
                ) \
                if score.personal_best_score else 0

        # Submit to database
        score_object = score.to_database()
        score_object.client_hash = score.client_hash

        if not config.ALLOW_RELAX and score.relaxing:
            score_object.status_pp = -1

        score.session.add(score_object)
        score.session.flush()

        # Try to upload replay
        app.session.executor.submit(
            upload_replay,
            score,
            score_object.id
        ).add_done_callback(
            utils.thread_callback
        )

        score.session.commit()

    new_stats, old_stats = update_stats(score, player)

    if not score.beatmap.is_ranked:
        score.session.close()
        app.session.events.submit(
            'user_update',
            user_id=player.id,
            mode=score.mode.value
        )
        return 'error: beatmap'

    if not config.ALLOW_RELAX and score.relaxing:
        score.session.close()
        app.session.events.submit(
            'user_update',
            user_id=player.id,
            mode=score.mode.value
        )
        return 'error: no'

    achievement_response: List[str] = []

    # TODO: Enable achievements for relax?
    if score.passed and not score.relaxing:
        achievement_response = unlock_achievements(
            score,
            score_object,
            player,
            request
        )

    new_rank = scores.fetch_score_index_by_tscore(
        score_object.total_score,
        score.beatmap.id,
        mode=score.mode.value,
        session=score.session
    )

    response = response_charts(
        score,
        score_object.id,
        old_stats,
        new_stats,
        old_rank,
        new_rank,
        achievement_response
    )

    app.session.logger.info(
        f'"{score.username}" submitted {"failed " if score.failtime else ""}score on {score.beatmap.full_name}'
    )

    score.session.close()

    # Send highlights on #announce
    if score.has_pb:
        app.session.executor.submit(
            app.highlights.check,
            score_object.id, score.user,
            new_stats, old_stats,
            new_rank, old_rank
        ).add_done_callback(
            utils.thread_callback
        )

    # Reload stats on bancho
    app.session.events.submit(
        'user_update',
        user_id=player.id,
        mode=score.mode.value
    )

    return "\n".join([chart.get() for chart in response])

@router.post('/osu-submit.php')
@router.post('/osu-submit-new.php')
def legacy_score_submission(
    request: Request,
    password: Optional[str] = Query(None, alias='pass'),
    score: Score = Depends(parse_score_data)
) -> str:
    score.user = users.fetch_by_name(
        score.username,
        score.session
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

    score.beatmap = beatmaps.fetch_by_checksum(
        score.file_checksum,
        score.session
    )

    if not score.beatmap:
        app.session.logger.warning(f'Failed to submit score: Beatmap not found')
        raise HTTPException(404)

    if not status.exists(player.id):
        return ''

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
        score.session
    )

    score.pp = score.calculate_ppv2()
    score.ppv1 = score.calculate_ppv1()

    if (error := perform_score_validation(score, player)) != None:
        raise HTTPException(400, detail=error.body.decode())

    if score.relaxing:
        # Recalculate rx total score
        object = score.to_database()
        object.beatmap = score.beatmap
        object.user = score.user
        score.total_score = calculate_rx_score(object)

    if score.version <= 0:
        # Client didn't provide a version
        # Try to get it from bancho instead
        score.version = status.version(player.id) or 0

    if score.version < 452 and Mods.Nightcore in score.enabled_mods:
        # Prevent "Taiko" mod plays from being submitted
        raise HTTPException(400)

    if score.beatmap.is_ranked:
        score.personal_best_pp = scores.fetch_personal_best(
            score.beatmap.id,
            score.user.id,
            score.mode.value,
            session=score.session
        )

        score.personal_best_score = scores.fetch_personal_best_score(
            score.beatmap.id,
            score.user.id,
            score.mode.value,
            session=score.session
        )

        score.status_pp = score.calculate_pp_status()
        score.status_score = score.calculate_score_status()

        # Get old rank before submitting score
        old_rank = scores.fetch_score_index_by_id(
                    score.personal_best_pp.id,
                    score.beatmap.id,
                    mode=score.mode.value,
                    session=score.session
                ) \
                if score.personal_best_score else 0

        # Submit to database
        score_object = score.to_database()
        score_object.client_hash = ''

        if not config.ALLOW_RELAX and score.relaxing:
            score_object.status_pp = -1

        score.session.add(score_object)
        score.session.flush()

        # Try to upload replay
        app.session.executor.submit(
            upload_replay,
            score,
            score_object.id
        ).add_done_callback(
            utils.thread_callback
        )

        score.session.commit()

    new_stats, old_stats = update_stats(score, player)

    if not score.beatmap.is_ranked:
        app.session.events.submit(
            'user_update',
            user_id=player.id,
            mode=score.mode.value
        )
        score.session.close()
        return

    if not config.ALLOW_RELAX and score.relaxing:
        app.session.events.submit(
            'user_update',
            user_id=player.id,
            mode=score.mode.value
        )
        score.session.close()
        return

    app.session.logger.info(
        f'"{score.username}" submitted {"failed " if score.failtime else ""}score on {score.beatmap.full_name}'
    )

    if not score.passed:
        app.session.events.submit(
            'user_update',
            user_id=player.id,
            mode=score.mode.value
        )
        score.session.close()
        return

    achievement_response: List[str] = []
    response: List[Chart] = []

    if not score.relaxing:
        achievement_response = unlock_achievements(
            score,
            score_object,
            player,
            request
        )

    beatmap_rank = scores.fetch_score_index_by_id(
        score_object.id,
        score.beatmap.id,
        mode=score.mode.value,
        session=score.session
    )

    # Reload stats on bancho
    app.session.events.submit(
        'user_update',
        user_id=player.id,
        mode=score.mode.value
    )

    if score.is_performance_pb:
        response.append(str(beatmap_rank))
    else:
        response.append('0')

    difference, next_user = leaderboards.player_above(
        player.id,
        score.mode.value
    )

    response.append(str(round(difference)))
    response.append(" ".join(achievement_response))

    score.session.close()

    # Send highlights on #announce
    if score.has_pb:
        app.session.executor.submit(
            app.highlights.check,
            score_object.id, score.user,
            new_stats, old_stats,
            beatmap_rank, old_rank
        ).add_done_callback(
            utils.thread_callback
        )

    return "\n".join(response)
