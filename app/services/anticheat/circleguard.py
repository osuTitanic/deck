
from circleguard import Circleguard

from app.objects import Score

from .replay import Replay
from .loader import Loader

import config
import utils
import app

class Anticheat:
    def __init__(self) -> None:
        self.loader = Loader(None, write_to_cache=False)
        self.cg = Circleguard(None, loader=self.loader)

    def perform_checks(self, score: Score, id: int):
        replay = Replay(score)

        if not score.replay:
            return

        details = []

        ur = self.cg.ur(replay)
        frametime = self.cg.frametime(replay)
        snaps = self.cg.snaps(
            replay,
            config.MAX_SNAP_ANGLE,
            config.MIN_SNAP_DISTANCE
        )

        if ur <= config.MAX_UR:
            details.append(f'{ur} ur.')

        if frametime <= config.MAX_FRAMETIME:
            details.append(f'{frametime} avg frametime')

        if snaps:
            details.append(f'{len(snaps)} snaps')

        if details:
            self.send_report(
                player_id=score.user.id,
                score_id=id,
                details='\n    '.join(details)
            )

    def send_report(self, player_id: int, score_id: int, details: str):
        player = app.session.database.user_by_id(player_id)

        message = '\n'.join((
             'Circleguard Anticheat Report:',
            f'  Player: {player.name if player else None} ({player_id})',
            f'  Score: {score_id}',
             '  Details:',
             '    '
        )) + details

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
