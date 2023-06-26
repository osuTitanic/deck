
from typing   import List, Optional
from datetime import datetime

from .constants import Mod, Mode, Grade, ScoreStatus
from .common.objects import DBScore

import hashlib
import app

class ClientHash:
    def __init__(self, md5: str, adapters: str, adapters_md5: str, uninstall_id: str, diskdrive_signature: str) -> None:
        self.diskdrive_signature = diskdrive_signature
        self.uninstall_id = uninstall_id
        self.adapters_md5 = adapters_md5
        self.adapters = adapters
        self.md5 = md5

    @property
    def string(self) -> str:
        return f'{self.md5}:{self.adapters}:{self.adapters_md5}:{self.uninstall_id}:{self.diskdrive_signature}'

    def __repr__(self) -> str:
        return self.string

    @classmethod
    def from_string(cls, string: str):
        try:
            md5, adapters, adapters_md5, uninstall_id, diskdrive_signature = string.split(':')
        except ValueError:
            args = string.split(':')

            md5 = args[0]
            adapers = args[1]
            adapters_md5 = args[2]

            diskdrive_signature = hashlib.md5(b'unknown').hexdigest()
            uninstall_id = hashlib.md5(b'unknown').hexdigest()

            try:
                uninstall_id = args[3]
                diskdrive_signature = args[4]
            except IndexError:
                pass

        return ClientHash(
            md5,
            adapters,
            adapters_md5,
            uninstall_id,
            diskdrive_signature
        )

class Score:
    def __init__(
        self,
        file_checksum: str,
        username: str,
        score_checksum: str,
        count300: int,
        count100: int,
        count50: int,
        countGeki: int,
        countKatu: int,
        countMiss: int,
        total_score: int,
        max_combo: int,
        perfect: bool,
        grade: Grade,
        enabled_mods: Mod,
        passed: bool,
        play_mode: Mode,
        date: datetime,
        version: int,
        flags: int,
        exited: bool,
        failtime: int,
        replay: Optional[bytes]
    ) -> None:
        self.file_checksum  = file_checksum
        self.username       = username
        self.score_checksum = score_checksum

        self.c300     = count300
        self.c100     = count100
        self.c50      = count50
        self.cGeki    = countGeki
        self.cKatu    = countKatu
        self.cMiss    = countMiss

        self.total_score  = total_score
        self.max_combo    = max_combo
        self.perfect      = perfect
        self.grade        = grade
        self.enabled_mods = enabled_mods

        self.passed    = passed
        self.play_mode = play_mode
        self.date      = date
        self.version   = version
        self.exited    = exited
        self.failtime  = failtime
        self.flags     = flags

        self.replay = replay

        self.personal_best: Optional[DBScore] = None
        self._pp: Optional[float] = None

        self.beatmap = app.session.database.beatmap_by_checksum(self.file_checksum)
        self.user    = app.session.database.user_by_name(self.username)
        self.session = app.session.database.session

        if self.beatmap:
            self.personal_best = app.session.database.personal_best(self.beatmap.id, self.user.id)
    
    def __repr__(self) -> str:
        return f'<Score {self.username} ({self.score_checksum})>'

    @property
    def total_hits(self) -> int:
        if self.play_mode == Mode.CatchTheBeat: 
            return self.c50 + self.c100 + self.c300 + self.cMiss + self.cKatu

        elif self.play_mode == Mode.OsuMania:
            return self.c300 + self.c100 + self.c50 + self.cGeki + self.cKatu + self.cMiss

        return self.c50 + self.c100 + self.c300 + self.cMiss

    @property
    def accuracy(self) -> float:
        if self.total_hits == 0:
            return 0.0

        if self.play_mode == Mode.Osu:
            return (
                ((self.c300 * 300.0) + (self.c100 * 100.0) + (self.c50 * 50.0))
                / (self.total_hits * 300.0)
            )

        elif self.play_mode == Mode.Taiko:
            return ((self.c100 * 0.5) + self.c300) / self.total_hits

        elif self.play_mode == Mode.CatchTheBeat:
            return (self.c300 + self.c100 + self.c50) / self.total_hits

        elif self.play_mode == Mode.OsuMania:
            return  (
                        (
                          (self.c50 * 50.0) + (self.c100 * 100.0) + (self.cKatu * 200.0) + ((self.c300 + self.cGeki) * 300.0)
                        )
                        / (self.total_hits * 300.0)
                    )

        else:
            app.session.logger.error('what?')
            return 0.0

    @property
    def relaxing(self) -> bool:
        return (Mod.Relax in self.enabled_mods) or (Mod.Autopilot in self.enabled_mods)

    @property
    def status(self) -> ScoreStatus:
        if self.passed:
            if not self.personal_best:
                # No pb has been set
                return ScoreStatus.Best

            if self.total_score > self.personal_best.total_score:
                # Change status of old pb
                self.personal_best.status = ScoreStatus.Submitted.value
                self.session.query(DBScore).filter(DBScore.id == self.personal_best.id) \
                    .update(
                        {'status': ScoreStatus.Submitted.value}
                    )
                self.session.commit()

                return ScoreStatus.Best

            return ScoreStatus.Submitted

        return ScoreStatus.Exited if self.exited else ScoreStatus.Failed

    @property
    def pp(self) -> float:
        return 0.0 # TODO


    @classmethod
    def parse(
        cls,
        formatted_string: str,
        replay: Optional[bytes],
        exited: bool,
        failtime: int
    ):
        items = formatted_string.split(':')

        return Score(
            file_checksum = items[0],
            username = items[1],
            score_checksum = items[2],
            count300 = int(items[3]),
            count100 = int(items[4]),
            count50 = int(items[5]),
            countGeki = int(items[6]),
            countKatu = int(items[7]),
            countMiss = int(items[8]),
            total_score = int(items[9]),
            max_combo = int(items[10]),
            perfect = items[11].lower() == 'true',
            grade = Grade[items[12]],
            enabled_mods = Mod(int(items[13])),
            passed = items[14].lower() == 'true',
            play_mode = Mode(int(items[15])),
            date = items[16],
            version = int(items[17].strip()),
            flags = items[17].count(' '),
            exited = exited,
            failtime = failtime,
            replay = replay
        )
    
    def to_database(self) -> DBScore:
        return DBScore(
            beatmap_id = self.beatmap.id,
            user_id = self.user.id,
            client_version = self.version,
            score_checksum = self.score_checksum,
            mode = self.play_mode.value,
            pp = round(self.pp, 8),
            acc = round(self.accuracy, 8),
            total_score = self.total_score,
            max_combo = self.max_combo,
            mods = self.enabled_mods.value,
            perfect = self.perfect,
            n300 = self.c300,
            n100 = self.c100,
            n50 = self.c50,
            nMiss = self.cMiss,
            nGeki = self.cGeki,
            nKatu = self.cKatu,
            grade = self.grade.name,
            status = self.status.value,
            replay = self.replay,
            failtime = self.failtime,
            replay_md5 = hashlib.md5(
                self.replay
            ).hexdigest() if self.replay else None
        )
