
from app.helpers.enums import BadFlags
from app.common.config import config_instance as config
from app.common.database.repositories import scores
from app.common.helpers import performance, replays
from app.common import officer
from app.common.database import (
    DBBeatmap,
    DBScore,
    DBUser
)
from app.common.constants import (
    ScoreStatus,
    GameMode,
    Grade,
    Mods
)
from sqlalchemy.orm import Session
from datetime import datetime

import hashlib
import re

MAX_PROCESS_LINE_LENGTH = 2048 # Prevent processing long lines
MAX_PROCESS_NUM_LINES = 1000 # Prevent processing too many lines
PROCESS_LIST_LEFT_PATTERN = re.compile(r"^([a-fA-F0-9]{32})\s+(.*)") # checked for redos

# <md5> <full_path> | <process_name> (<window_title>)
class ScoreProcess:
    def __init__(
        self,
        full_line: str,
        md5: str | None,
        full_path: str | None,
        process_name: str | None,
        window_title: str | None
    ) -> None:
        self.full_line = full_line
        self.md5 = md5
        self.full_path = full_path
        self.process_name = process_name
        self.window_title = window_title

    @classmethod
    def from_line(cls, line: str) -> ScoreProcess | None:
        if line is None:
            return None

        if len(line) > MAX_PROCESS_LINE_LENGTH:
            return cls(
                full_line=line, 
                md5=None, 
                full_path=None, 
                process_name=None, 
                window_title=None)

        line = line.strip()

        # using a full regex here is prone to a ReDoS because of | and ( character backtracks
        # to avoid headaches just using simpler methods

        if " | " not in line:
            return cls(
                full_line=line,
                md5=None, 
                full_path=None, 
                process_name=None, 
                window_title=None
            )

        md5 = None
        full_path = None
        process_name = None
        window_title = None

        left, right = line.split(" | ", 1)
        match_left = PROCESS_LIST_LEFT_PATTERN.match(left)

        if match_left:
            md5 = match_left.group(1)
            full_path = match_left.group(2)
        else:
            full_path = left

        if " (" in right:
            process_name, _, window_title = right.partition(" (")

            if window_title and window_title.endswith(")"):
                window_title = window_title[:-1]
            
        else:
            process_name = right
        
        return cls(
            full_line=line,
            md5=md5, 
            full_path=full_path, 
            process_name=process_name,
            window_title=window_title
        )

# AABBCCDDEEFF.AABBCCDDEEFF.AABBCCDDEEFF.. (empty is fine, but normally 6 bytes uppercase)
class ScoreNetworkAdapter():
    def __init__(
        self,
        physical_address: str | None
    ) -> None:
        self.physical_address = physical_address

    @classmethod
    def from_adapter_list (cls, part: str | None) -> list[ScoreNetworkAdapter] | None:
        if part is None:
            return None
        
        return [cls(physical_address=addr) for addr in part.split(".")]

# <osu!.exe md5>:<MAC Address[0].MAC Address[1]>:<MAC Address combined md5>:<UniqueId md5>:<UniqueId2 md5>:
class ScoreSecurityHash:
    def __init__(
        self,
        osu_exe_md5: str | None,
        network_adapters: list[ScoreNetworkAdapter] | None,
        network_adapters_md5: str | None,
        unique_id_md5: str | None,
        unique_id2_md5: str | None
    )
        self.osu_exe_md5 = osu_exe_md5
        self.network_adapters = network_adapters
        self.network_adapters_md5 = network_adapters_md5
        self.unique_id_md5 = unique_id_md5
        self.unique_id2_md5 = unique_id2_md5

    @staticmethod
    def validate_adapters_unprocessed(network_adapters_str: str, network_adapters_md5: str) -> bool:
        """Checks if md5(network_adapters_str) == network_adapters_md5"""
        return hashlib.md5(network_adapters_md5).hexdigest() == network_adapters_md5 # we can expect the network_adapters_md5 to be lowercase coming from the client

    def validate_adapters (self) -> bool:
        """Runs a check to make sure network_adapters_md5 is a real md5 of the network_adapters"""
        if network_adapters is None:
            return True
        
        if len(network_adapters) == 0:
            return True
        
        # We do an early check here because when we reconstruct the adapters using this value
        # we would get "runningunderwine." instead of "runningunderwine", causing the md5 to mismatch anyway.
        if network_adapters[0] == "runningunderwine": 
            return True

        network_adapter_str = "".join(f"{network_adapter.physical_address  or ''}." for adapter in self.network_adapters)
        return ScoreSecurityHash.validate_adapters_unprocessed(network_adapter_str, self.network_adapters_md5)

    @classmethod
    def from_string (cls, security_hash_str: str | None) -> ScoreSecurityHash | None:
        if part is None:
            return None
        
        osu_exe_md5 = None
        network_adapters = None
        network_adapters_md5 = None
        unique_id_md5 = None
        unique_id2_md5 = None

        parts = security_hash_str.split(":")
        for i, part in enumerate(parts[:5]): # we can't expect it to be uniform since there are hints that this was smaller (3 parts) at one point.
            if i == 0:
                osu_exe_md5 = part
            elif i == 1:
                network_adapters = ScoreNetworkAdapter.from_adapter_list(part)
            elif i == 2:
                network_adapters_md5 = part
            elif i == 3:
                unique_id_md5 = part
            elif i == 4:
                unique_id2_md5 = part
        
        return cls(
            osu_exe_md5=osu_exe_md5,
            network_adapters=network_adapters
            network_adapters_md5=network_adapters_md5,
            unique_id_md5=unique_id_md5
            unique_id2_md5=unique_id2_md5
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
        mode: GameMode,
        version: int,
        flags: BadFlags,
        exited: bool | None,
        failtime: int | None,
        replay: bytes | None
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
        self.failtime = failtime
        self.version_string = f"b{version}"
        self.version = version

        self.replay = replay
        self.status_pp = ScoreStatus.Submitted
        self.status_score = ScoreStatus.Submitted
        self.touchscreen = False
        self.is_legacy = True
        self.ppv1 = 0.0
        self.pp = 0.0

        self.personal_best_score: DBScore
        self.personal_best_pp: DBScore
        self.beatmap: DBBeatmap
        self.user: DBUser

        # Optional
        self.fun_spoiler: str | None = None
        self.client_hash: str | None = None
        self.processes: str | None = None

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
    def replay_filename(self) -> str:
        if not self.beatmap or not self.user:
            return f'{self.username} ({self.score_checksum}).osr'

        return f'{self.user.name} on {self.beatmap.full_name} ({self.score_checksum}).osr'

    @property
    def elapsed_time(self) -> int:
        """Total time elapsed for this score, in seconds"""
        if not self.beatmap:
            return 0

        if self.passed:
            return self.beatmap.total_length

        assert self.failtime is not None
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

    def calculate_ppv1(self, session: Session) -> float:
        score = self.to_database()
        result = performance.calculate_ppv1(score, session)

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

    def calculate_pp_status(self, session: Session) -> ScoreStatus:
        """Set the performance status of this score, and the personal best of the user

        The score "status" determines if a score is a
            - Personal best
            - Personal best with mod combination
            - Submitted score
            - Failed/Exited score
            - Hidden score
        """
        assert self.beatmap is not None, "Beatmap must be set to calculate pp status"
        assert self.user is not None, "User must be set to calculate pp status"

        if not config.ALLOW_RELAX and self.relaxing:
            return ScoreStatus.Hidden

        if self.relaxing:
            return ScoreStatus.Submitted if self.passed else ScoreStatus.Exited

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
                session
            )

            if not mods_pb:
                return ScoreStatus.Mods

            if self.total_score < mods_pb.total_score:
                return ScoreStatus.Submitted

            # Change status for old personal best
            session.query(DBScore) \
                .filter(DBScore.id == mods_pb.id) \
                .update({'status_pp': ScoreStatus.Submitted.value})
            session.flush()
            return ScoreStatus.Mods

        # New pb was set
        status: dict = (
            {'status_pp': ScoreStatus.Submitted.value}
            if self.enabled_mods.value == self.personal_best_pp.mods else
            {'status_pp': ScoreStatus.Mods.value}
        )

        session.query(DBScore) \
            .filter(DBScore.id == self.personal_best_pp.id) \
            .update(status)

        session.flush()
        return ScoreStatus.Best

    def calculate_score_status(self, session: Session) -> ScoreStatus:
        """Set the score status of this score, and the personal best of the user

        The score "status" determines if a score is a
            - Personal best
            - Personal best with mod combination
            - Submitted score
            - Failed/Exited score
            - Hidden score
        """
        assert self.beatmap is not None, "Beatmap must be set to calculate score status"
        assert self.user is not None, "User must be set to calculate score status"

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
                session
            )

            if not mods_pb:
                return ScoreStatus.Mods

            if self.total_score < mods_pb.total_score:
                return ScoreStatus.Submitted

            # Change status for old personal best
            session.query(DBScore) \
                .filter(DBScore.id == mods_pb.id) \
                .update({'status_score': ScoreStatus.Submitted.value})
            session.flush()
            return ScoreStatus.Mods

        # New pb was set
        status: dict = (
            {'status_score': ScoreStatus.Submitted.value}
            if self.enabled_mods.value == self.personal_best_score.mods else
            {'status_score': ScoreStatus.Mods.value}
        )

        session.query(DBScore) \
            .filter(DBScore.id == self.personal_best_score.id) \
            .update(status)

        session.flush()
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

    def serialize_replay(self) -> bytes | None:
        """Serialize the replay of this score into an .osr format"""
        if not self.replay:
            return None

        assert self.beatmap is not None, "Beatmap must be set to serialize replay"
        assert self.user is not None, "User must be set to serialize replay"
        score_object = self.to_database()
        score_object.beatmap = self.beatmap
        score_object.user = self.user
        score_object.id = 0
        return replays.serialize_replay(score_object, self.replay)

    @classmethod
    def parse(
        cls,
        formatted_string: str,
        replay: bytes | None,
        exited: bool | None,
        failtime: int | None
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
            client_string=self.version_string,
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
            touchscreen=self.touchscreen,
            failtime=self.failtime,
            submitted_at=datetime.now(),
            replay_md5=(
                hashlib.md5(self.replay).hexdigest()
                if self.replay else None
            )
        )
