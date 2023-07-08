
from circleguard import Circleguard

from app.objects import Score

from .replay import Replay
from .loader import Loader

import utils
import app

# TODO: Move to config
MIN_SNAP_DISTANCE = 8
MAX_SNAP_ANGLE = 10
MAX_FRAMETIME = 13
MAX_UR = 50

class Anticheat:
    def __init__(self) -> None:
        self.loader = Loader(None, write_to_cache=False)
        self.cg = Circleguard(None, loader=self.loader)

    def perform_checks(self, score: Score, id: int):
        replay = Replay(score)

        if not score.replay:
            return

        details = []

        snaps = self.cg.snaps(replay, MAX_SNAP_ANGLE, MIN_SNAP_DISTANCE)
        frametime = self.cg.frametime(replay)
        ur = self.cg.ur(replay)

        if ur <= MAX_UR:
            details.append(f'{ur} ur.')

        if frametime <= MAX_FRAMETIME:
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
