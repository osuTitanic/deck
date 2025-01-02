
from app.common.database.repositories import notifications, activities, scores, wrapper
from app.common.constants import Mods, NotificationType
from app.common import officer
from app.common.database import (
    DBBeatmap,
    DBScore,
    DBStats,
    DBUser
)

from sqlalchemy.orm import Session
from typing import List, Tuple

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
    session: Session,
    message: str,
    *args: List[Tuple[str]],
    submit_to_chat: bool = True,
) -> None:
    # TODO: Refactor activities to use json entries
    activities.create(
        user_id,
        mode,
        message,
        '||'.join([a[0] for a in args]),
        '||'.join([a[1] for a in args]),
        session=session
    )

    if not submit_to_chat:
        return

    irc_args = [
        f'[{a[1]} {a[0].replace("(", "[").replace(")", "]")}]'
        for a in args
    ]

    app.session.events.submit(
        'bot_message',
        message=message.format(*irc_args),
        target='#announce'
    )

def check_rank(
    new_stats: DBStats,
    previous_stats: DBStats,
    player: DBUser,
    mode_name: str,
    session: Session
) -> None:
    if new_stats.rank == previous_stats.rank:
        return

    ranks_gained = previous_stats.rank - new_stats.rank

    if new_stats.playcount > 1:
        if ranks_gained <= 0:
            return

    if previous_stats.rank <= 0:
        return

    if previous_stats.rank < 1000 <= new_stats.rank:
        # Player has risen to the top 1000
        return submit(
            player.id,
            new_stats.mode,
            session,
            '{} ' + f"has risen {ranks_gained} {'ranks' if ranks_gained != 1 else 'rank'}, now placed #{new_stats.rank} overall in {mode_name}.",
            (player.name, f'http://osu.{config.DOMAIN_NAME}/u/{player.id}'),
            submit_to_chat=False
        )

    if previous_stats.rank < 100 <= new_stats.rank:
        # Player has risen to the top 100
        return submit(
            player.id,
            new_stats.mode,
            session,
            '{} ' + f"has risen {ranks_gained} {'ranks' if ranks_gained != 1 else 'rank'}, now placed #{new_stats.rank} overall in {mode_name}.",
            (player.name, f'http://osu.{config.DOMAIN_NAME}/u/{player.id}'),
            submit_to_chat=False
        )

    if new_stats.rank >= 10 and new_stats.rank != 1:
        # Player has risen to the top 10 or above
        submit(
            player.id,
            new_stats.mode,
            session,
            '{} ' + f"has risen {ranks_gained} {'ranks' if ranks_gained != 1 else 'rank'}, now placed #{new_stats.rank} overall in {mode_name}.",
            (player.name, f'http://osu.{config.DOMAIN_NAME}/u/{player.id}')
        )

    if new_stats.rank == 1:
        # Player is now #1
        submit(
            player.id,
            new_stats.mode,
            session,
            '{} ' + f'has taken the lead as the top-ranked {mode_name} player.',
            (player.name, f'http://osu.{config.DOMAIN_NAME}/u/{player.id}')
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
    if score.status_pp != 3:
        # Score is not visible on global rankings
        return

    # Get short-from mods string (e.g. HDHR)
    mods = Mods(score.mods).short if score.mods > 0 else ""

    if beatmap_rank <= 1000:
        submit(
            player.id,
            score.mode,
            session,
            '{} ' + f'achieved rank #{beatmap_rank} on' + ' {} ' + f'{f"with {mods} " if mods else ""}<{mode_name}> ({round(score.pp)}pp)',
            (player.name, f'http://osu.{config.DOMAIN_NAME}/u/{player.id}'),
            (score.beatmap.full_name, f'http://osu.{config.DOMAIN_NAME}/b/{score.beatmap.id}'),
            submit_to_chat=(beatmap_rank <= 5)
        )

    if beatmap_rank != 1:
        return

    if old_rank == beatmap_rank:
        return

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
            session,
            '{} ' + 'has lost first place on' + ' {} ' + f'<{mode_name}>',
            (second_place.user.name, f'http://osu.{config.DOMAIN_NAME}/u/{second_place.user_id}'),
            (score.beatmap.full_name, f'http://osu.{config.DOMAIN_NAME}/b/{score.beatmap_id}'),
            submit_to_chat=False
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
            session,
            '{} ' + 'has set the new pp record on' + ' {} ' + f'with {round(score.pp)}pp <{mode_name}>',
            (player.name, f'http://osu.{config.DOMAIN_NAME}/u/{player.id}'),
            (score.beatmap.full_name, f'http://osu.{config.DOMAIN_NAME}/b/{score.beatmap.id}')
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
            session,
            '{} ' + 'got a new top play on' + ' {} ' + f'with {round(score.pp)}pp <{mode_name}>',
            (player.name, f'http://osu.{config.DOMAIN_NAME}/u/{player.id}'),
            (score.beatmap.full_name, f'http://osu.{config.DOMAIN_NAME}/b/{score.beatmap.id}'),
            submit_to_chat=False
        )

@wrapper.exception_wrapper(on_check_fail)
def check(
    player: DBUser,
    score: DBScore,
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
