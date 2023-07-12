
from app.common.objects import DBStats, DBUser, DBScore

import config
import utils

def send_message(message: str):
    utils.submit_to_queue(
        type='bot_message',
        data={
            'message': message,
            'target': '#highlight'
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
        send_message(
            f"{player.name} has risen {ranks_gained} ranks, now placed #{stats.rank} overall in {mode_name}."
        )

    if stats.rank == 1:
        # Player is now #1
        send_message(
            f"{player.name} has taken the lead as the top-ranked {mode_name} player."
        )

def check_beatmap(
    beatmap_rank: int,
    score: DBScore,
    player: DBUser,
    mode_name: str
):
    if beatmap_rank > config.SCORE_RESPONSE_LIMIT:
        return

    send_message(
        f"{player.name} achieved rank #{beatmap_rank} on ({score.beatmap.full_name})[http://{config.DOMAIN_NAME}/b/{score.beatmap_id}] ({mode_name})"
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

    # TODO: Achievements
    # TODO: PP Record?
