
from app.common.database.repositories import activities
from app.common.database.repositories import scores
from app.common.constants import Mods
from app.common.database import (
    DBBeatmap,
    DBScore,
    DBStats,
    DBUser
)

from typing import List, Tuple

import config
import app

def submit(user_id: int, mode: int, message: str, *args: List[Tuple[str]], submit_to_chat: bool = True):
    if submit_to_chat:
        try:
            irc_args = [
                f'[{a[1]} {a[0].replace("(", "[").replace(")", "]")}]'
                for a in args
            ]
            irc_message = message.format(*irc_args)

            app.session.events.submit(
                'bot_message',
                message=irc_message,
                target='#announce'
            )
        except Exception as e:
            app.session.logger.error(
                f'Failed to submit highlight message: {e}',
                exc_info=e
            )

    # TODO: Refactor activities to use json...
    try:
        activities.create(
            user_id,
            mode,
            message,
            '||'.join([a[0] for a in args]),
            '||'.join([a[1] for a in args])
        )
    except Exception as e:
        app.session.logger.error(
            f'Failed to submit highlight message to database: {e}',
            exc_info=e
        )

def check_rank(
    stats: DBStats,
    previous_stats: DBStats,
    player: DBUser,
    mode_name: str
):
    if stats.rank == previous_stats.rank:
        return

    ranks_gained = previous_stats.rank - stats.rank

    if stats.playcount > 1:
        if ranks_gained <= 0:
            return

    if previous_stats.rank < 1000 \
       and stats.rank >= 1000:
        # Player has risen to the top 1000
        submit(
            player.id,
            stats.mode,
            '{} ' + f"has risen {ranks_gained} {'ranks' if ranks_gained > 1 else 'rank'}, now placed #{stats.rank} overall in {mode_name}.",
            (player.name, f'http://osu.{config.DOMAIN_NAME}/u/{player.id}'),
            submit_to_chat=False
        )
        return

    if previous_stats.rank < 100 \
       and stats.rank >= 100:
        # Player has risen to the top 100
        submit(
            player.id,
            stats.mode,
            '{} ' + f"has risen {ranks_gained} {'ranks' if ranks_gained > 1 else 'rank'}, now placed #{stats.rank} overall in {mode_name}.",
            (player.name, f'http://osu.{config.DOMAIN_NAME}/u/{player.id}'),
            submit_to_chat=False
        )
        return

    if previous_stats.rank < 10 \
       and stats.rank >= 10:
        # Player has risen to the top 10
        submit(
            player.id,
            stats.mode,
            '{} ' + f"has risen {ranks_gained} {'ranks' if ranks_gained > 1 else 'rank'}, now placed #{stats.rank} overall in {mode_name}.",
            (player.name, f'http://osu.{config.DOMAIN_NAME}/u/{player.id}')
        )

    if stats.rank == 1:
        # Player is now #1
        submit(
            player.id,
            stats.mode,
            '{} ' + f'has taken the lead as the top-ranked {mode_name} player.',
            (player.name, f'http://osu.{config.DOMAIN_NAME}/u/{player.id}')
        )

def check_beatmap(
    beatmap_rank: int,
    old_rank: int,
    score: DBScore,
    player: DBUser,
    mode_name: str
):
    if score.status != 3:
        # Score is not visible on global rankings
        return

    # Get short-from mods string (e.g. HDHR)
    mods = Mods(score.mods).short if score.mods > 0 else ""

    if beatmap_rank != 1:
        # Score is not on the leaderboards
        # Check if score is in the top 1000

        if beatmap_rank >= 1000:
            submit(
                player.id,
                score.mode,
                '{} ' + f'achieved rank #{beatmap_rank} on' + ' {} ' + f'{f"with {mods} " if mods else ""}<{mode_name}>',
                (player.name, f'http://osu.{config.DOMAIN_NAME}/u/{player.id}'),
                (score.beatmap.full_name, f'http://osu.{config.DOMAIN_NAME}/b/{score.beatmap.id}'),
                submit_to_chat=False
            )

    submit(
        player.id,
        score.mode,
        '{} ' + f'achieved rank #{beatmap_rank} on' + ' {} ' + f'{f"with {mods} " if mods else ""}<{mode_name}>',
        (player.name, f'http://osu.{config.DOMAIN_NAME}/u/{player.id}'),
        (score.beatmap.full_name, f'http://osu.{config.DOMAIN_NAME}/b/{score.beatmap_id}')
    )

    if old_rank == beatmap_rank:
        return

    top_scores = scores.fetch_range_scores(
        score.beatmap_id,
        score.mode,
        limit=2
    )

    if len(top_scores) <= 1:
        return

    second_place = top_scores[1]

    submit(
        second_place.user_id,
        score.mode,
        '{} ' + 'has lost first place on' + ' {} ' + f'<{mode_name}>',
        (second_place.user.name, f'http://osu.{config.DOMAIN_NAME}/u/{second_place.user_id}'),
        (score.beatmap.full_name, f'http://osu.{config.DOMAIN_NAME}/b/{score.beatmap_id}'),
        submit_to_chat=False
    )


def check_pp(
    score: DBScore,
    player: DBUser,
    mode_name: str
):
    # Get current pp record for mode
    with app.session.database.managed_session() as session:
        result = session.query(DBScore) \
                .filter(DBScore.mode == score.mode) \
                .filter(DBScore.status == 3) \
                .order_by(DBScore.pp.desc()) \
                .first()

        if not result:
            # No score has been set, yet
            return

        if score.id == result.id:
            # Player has set the new pp record
            submit(
                player.id,
                score.mode,
                '{} ' + 'has set the new pp record on' + ' {} ' + f'with {round(score.pp)}pp <{mode_name}>',
                (player.name, f'http://osu.{config.DOMAIN_NAME}/u/{player.id}'),
                (score.beatmap.full_name, f'http://osu.{config.DOMAIN_NAME}/b/{score.beatmap.id}')
            )
            return

        # Check player's current top plays
        query = session.query(DBScore) \
                .filter(DBScore.mode == score.mode) \
                .filter(DBScore.user_id == player.id) \
                .filter(DBScore.status == 3)

        # Exclude approved map rewards if specified in the config
        if not config.APPROVED_MAP_REWARDS:
            query = query.filter(DBBeatmap.status == 1) \
                         .join(DBScore.beatmap)

        result = query.order_by(DBScore.pp.desc()) \
                      .first()

        if score.id == result.id:
            # Player got a new top play
            submit(
                player.id,
                score.mode,
                '{} ' + 'got a new top play on' + ' {} ' + f'with {round(score.pp)}pp <{mode_name}>',
                (player.name, f'http://osu.{config.DOMAIN_NAME}/u/{player.id}'),
                (score.beatmap.full_name, f'http://osu.{config.DOMAIN_NAME}/b/{score.beatmap.id}'),
                submit_to_chat=False
            )

def check(
    player: DBUser,
    stats: DBStats,
    previous_stats: DBStats,
    score: DBScore,
    beatmap_rank: int,
    old_rank: int
) -> None:
    mode_name = {
        0: "osu!",
        1: "Taiko",
        2: "CatchTheBeat",
        3: "osu!mania"
    }[stats.mode]

    check_rank(
        stats,
        previous_stats,
        player,
        mode_name
    )

    check_beatmap(
        beatmap_rank,
        old_rank,
        score,
        player,
        mode_name
    )

    check_pp(
        score,
        player,
        mode_name
    )
