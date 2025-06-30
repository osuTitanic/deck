
from app.common.database import notifications, activities, scores, wrapper
from app.common.constants import Mods, NotificationType, UserActivity
from app.common.cache import leaderboards
from sqlalchemy.orm import Session
from app.common import officer
from app.common.database import (
    DBBeatmap,
    DBScore,
    DBStats,
    DBUser
)

import config
import app

def on_submit_fail(e: Exception) -> None:
    officer.call(
        f'Failed to submit highlight: "{e}"',
        exc_info=e
    )

def on_check_fail(e: Exception) -> None:
    officer.call(
        f'Failed to check highlights: "{e}"',
        exc_info=e
    )

@wrapper.exception_wrapper(on_submit_fail)
def submit(
    user_id: int,
    mode: int,
    type: UserActivity,
    data: dict,
    session: Session,
    is_announcement: bool = False,
    is_hidden: bool = False
) -> None:
    app.session.events.submit(
        'bancho_event',
        user_id=user_id,
        mode=mode,
        type=type.value,
        data=data,
        is_announcement=is_announcement
    )

    if is_hidden:
        return

    activities.create(
        user_id, mode,
        type, data,
        session=session
    )

def check_rank(
    stats: DBStats,
    previous_stats: DBStats,
    player: DBUser,
    mode_name: str,
    session: Session
) -> None:
    if stats.rank == previous_stats.rank:
        return

    ranks_gained = previous_stats.rank - stats.rank

    if stats.playcount > 1:
        if ranks_gained <= 0:
            return

    if previous_stats.rank <= 0:
        return

    if previous_stats.rank < 1000 <= stats.rank:
        # Player has risen to the top 1000
        return submit(
            player.id,
            stats.mode,
            UserActivity.RanksGained,
            {
                "username": player.name,
                "ranks_gained": ranks_gained,
                "rank": stats.rank,
                "mode": mode_name
            },
            session
        )

    if previous_stats.rank < 100 <= stats.rank:
        # Player has risen to the top 100
        return submit(
            player.id,
            stats.mode,
            UserActivity.RanksGained,
            {
                "username": player.name,
                "ranks_gained": ranks_gained,
                "rank": stats.rank,
                "mode": mode_name
            },
            session,
            is_announcement=True
        )

    if stats.rank >= 10 and stats.rank != 1:
        # Player has risen to the top 10 or above
        submit(
            player.id,
            stats.mode,
            UserActivity.RanksGained,
            {
                "username": player.name,
                "ranks_gained": ranks_gained,
                "rank": stats.rank,
                "mode": mode_name
            },
            session,
            is_announcement=True
        )

    if stats.rank == 1:
        # Player is now #1
        submit(
            player.id,
            stats.mode,
            UserActivity.NumberOne,
            {
                "username": player.name,
                "mode": mode_name
            },
            session,
            is_announcement=True
        )

        notifications.create(
            player.id,
            NotificationType.Other.value,
            'Welcome to the top!',
            f'Congratulations for reaching the #1 global rank in {mode_name}.'
            ' Your incredible skill and dedication have set you apart as the absolute best in the game.'
            ' Best of luck on your continued journey at the top!',
            session=session
        )

def check_beatmap(
    beatmap_rank: int,
    old_rank: int,
    score: DBScore,
    player: DBUser,
    mode_name: str,
    session: Session
) -> None:
    if score.status_score != 3:
        # Score is not visible on global rankings
        return

    # Get short-from mods string (e.g. HDHR)
    mods = Mods(score.mods).short if score.mods > 0 else ""

    if beatmap_rank <= 1000:
        submit(
            player.id,
            score.mode,
            UserActivity.BeatmapLeaderboardRank,
            {
                "username": player.name,
                "beatmap": score.beatmap.full_name,
                "beatmap_id": score.beatmap.id,
                "beatmap_rank": beatmap_rank,
                "mode": mode_name,
                "mods": mods,
                "pp": round(score.pp or 0)
            },
            session,
            is_announcement=(beatmap_rank <= 4)
        )

    if beatmap_rank != 1:
        return

    if old_rank == beatmap_rank:
        return
    
    leaderboards.update_leader_scores(
        player.stats[score.mode],
        player.country.lower(),
        session=session
    )

    top_scores = scores.fetch_range_scores(
        score.beatmap_id,
        score.mode,
        limit=2,
        session=session
    )

    if len(top_scores) <= 1:
        return

    second_place = top_scores[1]

    if second_place.user_id != player.id:
        submit(
            second_place.user_id,
            score.mode,
            UserActivity.LostFirstPlace,
            {
                "username": second_place.user.name,
                "beatmap": score.beatmap.full_name,
                "beatmap_id": score.beatmap.id,
                "mode": mode_name
            },
            session
        )

        second_place.user.stats.sort(
            key=lambda x: x.mode,
            reverse=False
        )

        leaderboards.update_leader_scores(
            second_place.user.stats[score.mode],
            second_place.user.country.lower(),
            session=session
        )

def check_pp(
    score: DBScore,
    player: DBUser,
    mode_name: str,
    session: Session
) -> None:
    # Get current pp record for mode
    result = scores.fetch_pp_record(
        score.mode,
        session=session
    )

    if not result:
        # No score has been set, yet
        return

    if score.id == result.id:
        # Player has set the new pp record
        submit(
            player.id,
            score.mode,
            UserActivity.PPRecord,
            {
                "username": player.name,
                "beatmap": score.beatmap.full_name,
                "beatmap_id": score.beatmap.id,
                "pp": round(score.pp or 0),
                "mode": mode_name
            },
            session,
            is_announcement=True
        )
        return

    # Check player's current top plays
    query = session.query(DBScore) \
            .filter(DBScore.mode == score.mode) \
            .filter(DBScore.user_id == player.id) \
            .filter(DBScore.status_pp == 3) \
            .filter(DBScore.hidden == False)

    # Exclude approved map rewards if specified in the config
    if not config.APPROVED_MAP_REWARDS:
        query = query.filter(DBBeatmap.status in (1, 2)) \
                     .join(DBScore.beatmap)

    result = query.order_by(DBScore.pp.desc()) \
                  .first()

    if not result:
        # Player has no top plays
        return

    if score.id == result.id:
        # Player got a new top play
        submit(
            player.id,
            score.mode,
            UserActivity.TopPlay,
            {
                "username": player.name,
                "beatmap": score.beatmap.full_name,
                "beatmap_id": score.beatmap.id,
                "pp": round(score.pp),
                "mode": mode_name
            },
            session
        )

@wrapper.exception_wrapper(on_check_fail)
def check(
    score_id: int,
    player: DBUser,
    new_stats: DBStats,
    previous_stats: DBStats,
    new_rank: int,
    old_rank: int
) -> None:
    with app.session.database.managed_session() as session:
        mode_name = {
            0: "osu!",
            1: "Taiko",
            2: "CatchTheBeat",
            3: "osu!mania"
        }[new_stats.mode]

        score = scores.fetch_by_id(
            score_id,
            session=session
        )

        player.stats.sort(
            key=lambda x: x.mode,
            reverse=False
        )

        check_rank(
            new_stats,
            previous_stats,
            player,
            mode_name,
            session
        )

        check_beatmap(
            new_rank,
            old_rank,
            score,
            player,
            mode_name,
            session
        )

        check_pp(
            score,
            player,
            mode_name,
            session
        )
