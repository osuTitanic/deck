
from app.common.objects import DBStats, DBUser, DBScore

from typing import List, Tuple

import traceback
import config
import utils
import app

def submit(user_id: int, mode: int, message: str, *args: List[Tuple[str]]):
    try:
        irc_args = [
            f'[{a[1]} {a[0].replace("(", "[").replace(")", "]")}]'
            for a in args
        ]
        irc_message = message.format(*irc_args)

        utils.submit_to_queue(
            type='bot_message',
            data={
                'message': irc_message,
                'target': '#announce'
            }
        )
    except Exception as e:
        traceback.print_exc()
        app.session.logger.error(
            f'Failed to submit highlight message: {e}'
        )

    app.session.database.submit_activity(
        user_id,
        mode,
        message,
        '||'.join([a[0] for a in args]),
        '||'.join([a[1] for a in args])
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

    if ranks_gained <= 0:
        return

    if stats.rank >= 10:
        # Player has risen to the top 10
        submit(
            player.id,
            stats.mode,
            '{} ' + f"has risen {ranks_gained} ranks, now placed #{stats.rank} overall in {mode_name}.",
            (player.name, f'http://{config.DOMAIN_NAME}/u/{player.id}')
        )

    if stats.rank == 1:
        # Player is now #1
        submit(
            player.id,
            stats.mode,
            '{} ' + f'has taken the lead as the top-ranked {mode_name} player.',
            (player.name, f'http://{config.DOMAIN_NAME}/u/{player.id}')
        )

def check_beatmap(
    beatmap_rank: int,
    score: DBScore,
    player: DBUser,
    mode_name: str
):
    if score.status != 3:
        # Score is not on the leaderboards
        return

    if beatmap_rank > config.SCORE_RESPONSE_LIMIT:
        return

    submit(
        player.id,
        score.mode,
        '{} ' + f'achieved rank #{beatmap_rank} on' + ' {} ' + f'({mode_name})',
        (player.name, f'http://{config.DOMAIN_NAME}/u/{player.id}'),
        (score.beatmap.full_name, f'http://{config.DOMAIN_NAME}/b/{score.beatmap.id}')
    )

def check(
    player: DBUser,
    stats: DBStats,
    previous_stats: DBStats,
    score: DBScore,
    beatmap_rank: int
) -> None:
    mode_name = {
        0: "osu!",
        1: "taiko",
        2: "catch the beat",
        3: "mania"
    }[stats.mode]

    check_rank(
        stats,
        previous_stats,
        player,
        mode_name
    )

    check_beatmap(
        beatmap_rank,
        score,
        player,
        mode_name
    )

    # TODO: PP Record?
