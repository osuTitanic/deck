
from circleguard import Circleguard, JudgmentType

from app.constants import AnticheatFlags
from app.common.objects import DBScore
from app.objects import Score

from .replay import Replay
from .loader import Loader

import config
import utils
import app

class Anticheat:
    def __init__(self) -> None:
        try:
            self.loader = Loader(None, write_to_cache=False)
            self.cg = Circleguard(None, loader=self.loader)
        except:
            pass

    def perform_checks(self, score: Score, score_id: int):
        replay = Replay(score)

        flags = AnticheatFlags.Clean

        frametime = self.cg.frametime(replay)
        judgements = self.cg.judgments(replay)
        ur = self.cg.ur(replay)
        snaps = self.cg.snaps(
            replay,
            config.MAX_SNAP_ANGLE,
            config.MIN_SNAP_DISTANCE
        )

        hits = [
            sum([j.type.value for j in judgements if j.type == JudgmentType.Miss]),
            sum([j.type.value for j in judgements if j.type == JudgmentType.Hit300]),
            sum([j.type.value for j in judgements if j.type == JudgmentType.Hit100]),
            sum([j.type.value for j in judgements if j.type == JudgmentType.Hit50])
        ]

        score_hits = [
            score.cMiss,
            score.c300,
            score.c100,
            score.c50
        ]

        if hits != score_hits:
            flags = flags|AnticheatFlags.ScoreMismatch

        if ur <= config.MAX_UR:
            flags = flags|AnticheatFlags.UR

        if frametime <= config.MAX_FRAMETIME:
            flags = flags|AnticheatFlags.Frametime

        if snaps:
            flags = flags|AnticheatFlags.Snaps

        # TODO: total score check

        if flags:
            self.send_report(
                player_id=score.user.id,
                score_id=score_id,
                flags=flags
            )

    def send_report(self, player_id: int, score_id: int, flags: AnticheatFlags):
        player = app.session.database.user_by_id(player_id)
        score = app.session.database.score(score_id)

        message = f'Player "{player.name}" submitted score on {score.beatmap.link} ({score_id}):\n'
        message += f'Anticheat detected {flags.description}.'

        app.session.logger.warning(message)

        utils.submit_to_queue(
            type='bot_message',
            data={
                'message': message,
                'target': '#admin'
            }
        )

        app.session.database.submit_log(
            message,
            'warning',
            'anticheat'
        )

        instance = app.session.database.session
        instance.query(DBScore) \
                .filter(DBScore.id == score_id) \
                .update({
                    'ac_flags': flags.value
                })
