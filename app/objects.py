
from datetime import datetime
from typing import Optional

from app.common.helpers import performance
from app.common.database.repositories import (
    scores,
    users
)

from .common.database import (
    DBBeatmap,
    DBScore
)

from .common.constants import (
    ScoreStatus,
    GameMode,
    BadFlags,
    Grade,
    Mods
)

import hashlib
import math
import app

class Chart(dict):
    def entry(self, name: str, before, after):
        self[f'{name}Before'] = str(before) if before is not None else ''
        self[f'{name}After']  = str(after)  if after  is not None else ''

    def get(self):
        return self.__repr__()

    def __repr__(self) -> str:
        return "|".join(f"{str(k)}:{str(v)}" for k, v in self.items())

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
            adapters = args[1]
            adapters_md5 = args[2]

            diskdrive_signature = hashlib.md5(b'unknown').hexdigest()
            uninstall_id = hashlib.md5(b'unknown').hexdigest()

            try:
                uninstall_id = args[3]
                diskdrive_signature = args[4]
            except IndexError:
                # Hardware IDs are not supported
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
        enabled_mods: Mods,
        passed: bool,
        play_mode: GameMode,
        date: datetime,
        version: int,
        flags: BadFlags,
        exited: Optional[bool],
        failtime: Optional[int],
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
        self.status = ScoreStatus.Submitted
        self.pp = 0.0

        # Optional
        self.personal_best: Optional[DBScore] = None
        self.fun_spoiler: Optional[str] = None
        self.client_hash: Optional[str] = None
        self.processes: Optional[str] = None

        # TODO: Refactor that?
        # Beatmap needs to be bound to session
        self.session = app.session.database.session
        self.beatmap = self.session.query(DBBeatmap) \
                        .filter(DBBeatmap.md5 == file_checksum) \
                        .first()

        self.user = users.fetch_by_name(username)
        self.pp = self.calculate_ppv2()

        if self.beatmap:
            self.personal_best = scores.fetch_personal_best(
                self.beatmap.id,
                self.user.id,
                self.play_mode.value
            )

            self.status = self.get_status()

    def __repr__(self) -> str:
        return f'<Score {self.username} ({self.score_checksum})>'

    @property
    def total_hits(self) -> int:
        if self.play_mode == GameMode.CatchTheBeat:
            return self.c50 + self.c100 + self.c300 + self.cMiss + self.cKatu

        elif self.play_mode == GameMode.OsuMania:
            return self.c300 + self.c100 + self.c50 + self.cGeki + self.cKatu + self.cMiss

        return self.c50 + self.c100 + self.c300 + self.cMiss

    @property
    def accuracy(self) -> float:
        if self.total_hits == 0:
            return 0.0

        if self.play_mode == GameMode.Osu:
            return (
                ((self.c300 * 300.0) + (self.c100 * 100.0) + (self.c50 * 50.0))
                / (self.total_hits * 300.0)
            )

        elif self.play_mode == GameMode.Taiko:
            return ((self.c100 * 0.5) + self.c300) / self.total_hits

        elif self.play_mode == GameMode.CatchTheBeat:
            return (self.c300 + self.c100 + self.c50) / self.total_hits

        elif self.play_mode == GameMode.OsuMania:
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
        return (Mods.Relax in self.enabled_mods) or (Mods.Autopilot in self.enabled_mods)

    @property
    def has_invalid_mods(self) -> bool:
        """Check if score has invalid mod combinations, like DTHT, HREZ, etc..."""
        if not self.enabled_mods:
            # No mods are enabled
            return False

        # NOTE: There is a bug, where DT/NC, PF/SD are enabled at the same time

        if self.check_mods(Mods.DoubleTime|Mods.Nightcore):
            self.enabled_mods = self.enabled_mods & ~Mods.DoubleTime

        if self.check_mods(Mods.Perfect|Mods.SuddenDeath):
            self.enabled_mods = self.enabled_mods & ~Mods.SuddenDeath

        if self.check_mods(Mods.FadeIn|Mods.Hidden):
            self.enabled_mods = self.enabled_mods & ~Mods.FadeIn

        if self.check_mods(Mods.Easy|Mods.HardRock):
            return True

        if self.check_mods(Mods.HalfTime|Mods.DoubleTime):
            return True

        if self.check_mods(Mods.HalfTime|Mods.Nightcore):
            return True

        if self.check_mods(Mods.NoFail|Mods.SuddenDeath):
            return True

        if self.check_mods(Mods.NoFail|Mods.Perfect):
            return True

        if self.check_mods(Mods.Relax|Mods.Autopilot):
            return True

        if self.check_mods(Mods.SpunOut|Mods.Autopilot):
            return True

        if self.check_mods(Mods.Autoplay):
            return True

        return False

    def check_mods(self, mods: Mods) -> bool:
        """Check if score has a combination of mods enabled"""
        if not self.enabled_mods:
            return False

        return True if mods in self.enabled_mods else False

    def calculate_ppv2(self) -> float:
        score = self.to_database()
        result = performance.calculate_ppv2(score)

        if result is None:
            app.session.logger.warning('Failed to calculate pp: No result')
            return 0.0

        if math.isnan(result.pp):
            app.session.logger.warning(f'Failed to calculate pp: {result.pp} value')
            # mfw NaN pp
            return 0.0

        return result.pp

    def get_status(self) -> ScoreStatus:
        """Set the status of this score, and the personal best of the user

        The score "status" determines if a score is a
        - Personal best
        - Personal best with mod combination
        - Submitted score
        - Failed/Exited score
        - Hidden score
        """
        if not self.passed:
            return ScoreStatus.Exited if self.exited else ScoreStatus.Failed

        if not self.personal_best:
            return ScoreStatus.Best

        if (Mods.Relax in self.enabled_mods or
            Mods.Autopilot in self.enabled_mods):
            # PP will be used for rx/ap
            better_score = self.pp > self.personal_best.pp

        else:
            # Total Score will be used for non-rx
            better_score = self.total_score > self.personal_best.total_score

        if not better_score:
            if self.enabled_mods.value == self.personal_best.mods:
                return ScoreStatus.Submitted

            # Check pb with mods
            mods_pb = scores.fetch_personal_best(
                self.beatmap.id,
                self.user.id,
                self.play_mode.value,
                self.enabled_mods.value
            )

            if not mods_pb:
                return ScoreStatus.Mods

            if self.total_score < mods_pb.total_score:
                return ScoreStatus.Submitted

            # Change status for old personal best
            self.session.query(DBScore) \
                   .filter(DBScore.id == mods_pb.id) \
                   .update(
                       {'status': ScoreStatus.Submitted.value}
                   )
            self.session.commit()

            return ScoreStatus.Mods

        # New pb was set
        status = {'status': ScoreStatus.Submitted.value} \
                 if self.enabled_mods.value == self.personal_best.mods else \
                 {'status': ScoreStatus.Mods.value}

        self.session.query(DBScore) \
               .filter(DBScore.id == self.personal_best.id) \
               .update(status)

        self.session.commit()

        return ScoreStatus.Best

    @classmethod
    def parse(
        cls,
        formatted_string: str,
        replay: Optional[bytes],
        exited: Optional[bool],
        failtime: Optional[int]
    ):
        """Parse a score string"""
        items = formatted_string.split(':')

        try:
            version = int(items[17].strip())
            flags = BadFlags(items[17].count(' '))
        except IndexError:
            version = 0
            flags = BadFlags.Clean

        try:
            date = items[16]
        except IndexError:
            date = datetime.now()

        try:
            play_mode = GameMode(int(items[15]))
        except IndexError:
            play_mode = GameMode.Osu

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
            enabled_mods = Mods(int(items[13])),
            passed = items[14].lower() == 'true',
            play_mode = play_mode,
            date = date,
            version = version,
            flags = flags,
            exited = exited,
            failtime = failtime,
            replay = replay
        )

    def to_database(self) -> DBScore:
        """Turn this score into a `DBScore` object, which can be used with sqlalchemy"""
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
            failtime = self.failtime,
            replay_md5 = hashlib.md5(
                self.replay
            ).hexdigest() if self.replay else None
        )
