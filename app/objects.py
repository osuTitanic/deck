
from typing import Optional
from datetime import datetime
from app.common.database.repositories import scores
from app.common.helpers import performance
from app.common import officer
from app.common.database import (
    DBBeatmap,
    DBScore,
    DBUser
)

from app.common.constants import (
    ScoreStatus,
    GameMode,
    BadFlags,
    Grade,
    Mods
)

import hashlib
import config
import app

class Chart(dict):
    def entry(self, name: str, before, after):
        self[f'{name}Before'] = str(before) if before is not None else ''
        self[f'{name}After'] = str(after) if after is not None else ''

    def get(self):
        return self.__repr__()

    def __repr__(self) -> str:
        return "|".join(f"{str(k)}:{str(v)}" for k, v in self.items())

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
        mode: GameMode,
        version: int,
        flags: BadFlags,
        exited: Optional[bool],
        failtime: Optional[int],
        replay: Optional[bytes]
    ) -> None:
        self.file_checksum = file_checksum
        self.username = username
        self.score_checksum = score_checksum

        self.c300 = count300
        self.c100 = count100
        self.c50 = count50
        self.cGeki = countGeki
        self.cKatu = countKatu
        self.cMiss = countMiss

        self.total_score = total_score
        self.max_combo = max_combo
        self.perfect = perfect
        self.grade = grade
        self.enabled_mods = enabled_mods
        self.username = username

        self.mode = mode
        self.flags = flags
        self.passed = passed
        self.exited = exited
        self.version = version
        self.failtime = failtime

        self.replay = replay
        self.status_pp = ScoreStatus.Submitted
        self.status_score = ScoreStatus.Submitted
        self.is_legacy = True
        self.ppv1 = 0.0
        self.pp = 0.0

        self.session = app.session.database.session
        self.personal_best_score: Optional[DBScore] = None
        self.personal_best_pp: Optional[DBScore] = None
        self.beatmap: Optional[DBBeatmap] = None
        self.user: Optional[DBUser] = None

        # Optional
        self.fun_spoiler: Optional[str] = None
        self.client_hash: Optional[str] = None
        self.processes: Optional[str] = None

        if passed:
            # "Fix" for old clients
            self.failtime = None
            self.exited = None

    def __repr__(self) -> str:
        return f'<Score {self.username} ({self.score_checksum})>'
    
    @property
    def is_performance_pb(self) -> bool:
        return self.status_pp == ScoreStatus.Best
    
    @property
    def is_score_pb(self) -> bool:
        return self.status_score == ScoreStatus.Best
    
    @property
    def has_pb(self) -> bool:
        return self.is_performance_pb or self.is_score_pb

    @property
    def relaxing(self) -> bool:
        return (Mods.Relax in self.enabled_mods) or (Mods.Autopilot in self.enabled_mods)

    @property
    def elapsed_time(self) -> int:
        """Total time elapsed for this score, in seconds"""
        if self.passed:
            return self.beatmap.total_length

        return self.failtime // 1000

    @property
    def total_hits(self) -> int:
        """Total amount of note hits in this score"""
        if self.mode in (GameMode.OsuMania, GameMode.Taiko):
            # taiko uses geki & katu for hitting big notes with 2 keys
            # mania uses geki & katu for rainbow 300 & 200
            return self.c50 + self.c100 + self.c300 + self.cGeki + self.cKatu

        # standard and fruits
        return self.c50 + self.c100 + self.c300

    @property
    def total_objects(self) -> int:
        """Total amount of passed objects in this score, used for accuracy calculation"""
        if self.mode in (GameMode.Osu, GameMode.Taiko):
            return self.c50 + self.c100 + self.c300 + self.cMiss

        elif self.mode == GameMode.CatchTheBeat:
            return self.c50 + self.c100 + self.c300 + self.cKatu + self.cMiss

        else:
            return self.c50 + self.c100 + self.c300 + self.cGeki + self.cKatu + self.cMiss

    @property
    def accuracy(self) -> float:
        if self.total_objects == 0:
            return 0.0

        if self.mode == GameMode.Osu:
            return (
                ((self.c300 * 300.0) + (self.c100 * 100.0) + (self.c50 * 50.0))
                / (self.total_objects * 300.0)
            )

        elif self.mode == GameMode.Taiko:
            return (
                ((self.c100 * 0.5) + self.c300)
                / self.total_objects
            )

        elif self.mode == GameMode.CatchTheBeat:
            return (
                (self.c300 + self.c100 + self.c50)
                / self.total_objects
            )

        elif self.mode == GameMode.OsuMania:
            return (
                (
                  (self.c50 * 50.0) +
                  (self.c100 * 100.0) +
                  (self.cKatu * 200.0) +
                  ((self.c300 + self.cGeki) * 300.0)
                )
                / (self.total_objects * 300.0)
            )

        return 0.0

    def has_mods(self, mods: Mods) -> bool:
        """Check if score has a combination of mods enabled"""
        if not self.enabled_mods:
            return False

        return True if mods in self.enabled_mods else False
    
    def calculate_ppv1(self) -> float:
        score = self.to_database()
        result = performance.calculate_ppv1(score, self.session)

        if result is None:
            officer.call('Failed to calculate ppv1: No result')
            return 0.0

        return result

    def calculate_ppv2(self) -> float:
        score = self.to_database()
        result = performance.calculate_ppv2(score)

        if result is None:
            officer.call('Failed to calculate pp: No result')
            return 0.0

        return result

    def calculate_pp_status(self) -> ScoreStatus:
        """Set the performance status of this score, and the personal best of the user

        The score "status" determines if a score is a
            - Personal best
            - Personal best with mod combination
            - Submitted score
            - Failed/Exited score
            - Hidden score
        """
        if not config.ALLOW_RELAX and self.relaxing:
            return ScoreStatus.Hidden

        if not self.passed:
            return ScoreStatus.Exited if self.exited else ScoreStatus.Failed

        if not self.personal_best_pp:
            return ScoreStatus.Best

        # Use pp to determine the better score, but fallback
        # to total score, if the pp is the same (spin to win)
        better_score = (
            self.pp > self.personal_best_pp.pp
            if round(self.pp) != round(self.personal_best_pp.pp)
            else self.total_score > self.personal_best_pp.total_score
        )

        if not better_score:
            if self.enabled_mods.value == self.personal_best_pp.mods:
                return ScoreStatus.Submitted

            # Check pb with mods
            mods_pb = scores.fetch_personal_best(
                self.beatmap.id,
                self.user.id,
                self.mode.value,
                self.enabled_mods.value,
                self.session
            )

            if not mods_pb:
                return ScoreStatus.Mods

            if self.total_score < mods_pb.total_score:
                return ScoreStatus.Submitted

            # Change status for old personal best
            self.session.query(DBScore) \
                .filter(DBScore.id == mods_pb.id) \
                .update({'status_pp': ScoreStatus.Submitted.value})
            self.session.commit()
            return ScoreStatus.Mods

        # New pb was set
        status = {'status_pp': ScoreStatus.Submitted.value} \
            if self.enabled_mods.value == self.personal_best_pp.mods else \
            {'status_pp': ScoreStatus.Mods.value}

        self.session.query(DBScore) \
            .filter(DBScore.id == self.personal_best_pp.id) \
            .update(status)

        self.session.commit()
        return ScoreStatus.Best
    
    def calculate_score_status(self) -> ScoreStatus:
        """Set the score status of this score, and the personal best of the user

        The score "status" determines if a score is a
            - Personal best
            - Personal best with mod combination
            - Submitted score
            - Failed/Exited score
            - Hidden score
        """
        if not config.ALLOW_RELAX and self.relaxing:
            return ScoreStatus.Hidden

        if not self.passed:
            return ScoreStatus.Exited if self.exited else ScoreStatus.Failed

        if not self.personal_best_score:
            return ScoreStatus.Best

        # Use score to determine the better score
        better_score = (
            self.total_score > self.personal_best_score.total_score
        )

        if not better_score:
            if self.enabled_mods.value == self.personal_best_score.mods:
                return ScoreStatus.Submitted

            # Check pb with mods
            mods_pb = scores.fetch_personal_best_score(
                self.beatmap.id,
                self.user.id,
                self.mode.value,
                self.enabled_mods.value,
                self.session
            )

            if not mods_pb:
                return ScoreStatus.Mods

            if self.total_score < mods_pb.total_score:
                return ScoreStatus.Submitted

            # Change status for old personal best
            self.session.query(DBScore) \
                .filter(DBScore.id == mods_pb.id) \
                .update({'status_score': ScoreStatus.Submitted.value})
            self.session.commit()
            return ScoreStatus.Mods

        # New pb was set
        status = {'status_score': ScoreStatus.Submitted.value} \
            if self.enabled_mods.value == self.personal_best_score.mods else \
            {'status_score': ScoreStatus.Mods.value}

        self.session.query(DBScore) \
            .filter(DBScore.id == self.personal_best_score.id) \
            .update(status)

        self.session.commit()
        return ScoreStatus.Best

    def check_invalid_mods(self) -> bool:
        """Check if score has invalid mod combinations, like DTHT, HREZ, etc..."""
        if not self.enabled_mods:
            return False

        # NOTE: The client is somehow sending these kinds of mod values.
        #       The wiki says it's normal, so shruge...
        #       https://github.com/ppy/osu-api/wiki#mods

        if self.has_mods(Mods.DoubleTime | Mods.Nightcore):
            self.enabled_mods = self.enabled_mods & ~Mods.DoubleTime

        if self.has_mods(Mods.Perfect | Mods.SuddenDeath):
            self.enabled_mods = self.enabled_mods & ~Mods.SuddenDeath

        if self.has_mods(Mods.FadeIn | Mods.Hidden):
            self.enabled_mods = self.enabled_mods & ~Mods.FadeIn

        if self.has_mods(Mods.Easy | Mods.HardRock):
            return True

        if self.has_mods(Mods.HalfTime | Mods.DoubleTime):
            return True

        if self.has_mods(Mods.HalfTime | Mods.Nightcore):
            return True

        if self.has_mods(Mods.NoFail | Mods.SuddenDeath):
            return True

        if self.has_mods(Mods.NoFail | Mods.Perfect):
            return True

        if self.has_mods(Mods.Relax | Mods.Autopilot):
            return True

        if self.has_mods(Mods.SpunOut | Mods.Autopilot):
            return True

        if self.has_mods(Mods.Autoplay):
            return True

        return False

    @classmethod
    def parse(
        cls,
        formatted_string: str,
        replay: Optional[bytes],
        exited: Optional[bool],
        failtime: Optional[int]
    ) -> "Score":
        """Parse a score string"""
        args = formatted_string.split(':')
        flags = BadFlags.Clean
        mode = GameMode.Osu
        version = 0

        if len(args) > 15:
            mode = GameMode(int(args[15]))

        if len(args) > 17:
            version = int(args[17].strip())
            flags = BadFlags(args[17].count(' '))

        return Score(
            file_checksum=args[0],
            username=args[1].strip(),
            score_checksum=args[2],
            count300=int(args[3]),
            count100=int(args[4]),
            count50=int(args[5]),
            countGeki=int(args[6]),
            countKatu=int(args[7]),
            countMiss=int(args[8]),
            total_score=int(args[9]),
            max_combo=int(args[10]),
            perfect=args[11].lower() == 'true',
            grade=Grade[args[12]],
            enabled_mods=Mods(int(args[13])),
            passed=args[14].lower() == 'true',
            mode=mode,
            version=version,
            flags=flags,
            exited=exited,
            failtime=failtime,
            replay=replay
        )

    def to_database(self) -> DBScore:
        """Convert this object into a `DBScore` object, which can be used with sqlalchemy"""
        return DBScore(
            beatmap_id=self.beatmap.id,
            user_id=self.user.id,
            client_version=self.version,
            checksum=self.score_checksum,
            mode=self.mode.value,
            pp=round(self.pp, 8),
            ppv1=round(self.ppv1, 8),
            acc=round(self.accuracy, 8),
            total_score=self.total_score,
            max_combo=self.max_combo,
            mods=self.enabled_mods.value,
            perfect=self.perfect,
            n300=self.c300,
            n100=self.c100,
            n50=self.c50,
            nMiss=self.cMiss,
            nGeki=self.cGeki,
            nKatu=self.cKatu,
            grade=self.grade.name,
            status_pp=self.status_pp.value,
            status_score=self.status_score.value,
            failtime=self.failtime,
            submitted_at=datetime.now(),
            replay_md5=(
                hashlib.md5(self.replay).hexdigest()
                if self.replay else None
            )
        )
