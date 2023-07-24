
from app.common.objects import DBStats, DBUser, DBScore

from typing import List, Tuple

import config
import utils

def submit(message: str, *args: List[Tuple[str, str]]):
    irc_args = [
        f'[{a[0].replace("(", "[").replace(")", "]")}]({a[1]})'
        for a in args
    ]
    irc_message = message.format(irc_args)

    utils.submit_to_queue(
        type='bot_message',
        data={
            'message': irc_message,
            'target': '#announce'
        }
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
            '{} ' + f"has risen {ranks_gained} ranks, now placed #{stats.rank} overall in {mode_name}.",
            (player.name, f'http://{config.DOMAIN_NAME}/u/{player.id}')
        )

    if stats.rank == 1:
        # Player is now #1
        submit(
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
