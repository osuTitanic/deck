
from circleguard.loadables import Replay as CircleguardReplay
from circleguard.game_version import GameVersion
from circleguard import RatelimitWeight

from osrparse import parse_replay_data
from slider.beatmap import Beatmap
from ossapi.mod import Mod

from datetime import datetime

from app.objects import Score

import app

class Replay(CircleguardReplay):
    def __init__(self, score: Score, cache=False):
        super().__init__(RatelimitWeight.NONE, cache)
        self.score = score
        self.loaded = False

    def beatmap(self, library):
        file = app.session.storage.get_beatmap(self.beatmap_id)

        if not file:
            return None

        return Beatmap.parse(file.decode())

    def load(self, loader, cache):
        if self.loaded:
            return

        self.mods = Mod(self.score.enabled_mods)
        self.game_version = GameVersion(self.score.version, True)
        self.username = self.score.username
        self.timestamp = datetime.now()
        self.beatmap_id = self.score.beatmap.id

        replay = self.score.replay

        if replay:
            replay = parse_replay_data(replay, decoded=True)
        else:
            replay = None
            return

        self._process_replay_data(replay)
        self.loaded = True

    def __eq__(self, other):
        return self.replay_id == other.replay_id

    def __hash__(self):
        return hash(self.replay_id)
