
from enum import Enum, IntEnum, IntFlag

class SubmissionStatus(Enum):
    Unknown        = 0
    NotSubmitted   = 1
    Pending        = 2
    EditableCutoff = 3
    Ranked         = 4
    Approved       = 5

    @classmethod
    def from_db(cls, value: int):
        return {
            -2: SubmissionStatus.Pending,        # Graveyard
            -1: SubmissionStatus.EditableCutoff, # WIP
            0:  SubmissionStatus.Pending,        # Pending
            1:  SubmissionStatus.Ranked,         # Ranked
            2:  SubmissionStatus.Approved,       # Approved
            3:  SubmissionStatus.Ranked,         # Qualified
            4:  SubmissionStatus.Approved        # Loved
        }[value]

class RankingType(Enum):
    Local       = 0
    Top         = 1
    SelectedMod = 2
    Friends     = 3
    Country     = 4

class CommentTarget(str, Enum):
    Replay = 'replay'
    Song   = 'song'
    Map    = 'map'

class Mode(IntEnum):
    Osu          = 0
    Taiko        = 1
    CatchTheBeat = 2
    OsuMania     = 3

class Permissions(IntFlag):
    NoPermissions = 0
    Normal        = 1
    BAT           = 2
    Subscriber    = 4
    Friend        = 8
    Admin         = 16

class Mod(IntFlag):
    NoMod          = 0
    NoFail         = 1
    Easy           = 2
    Hidden         = 8
    HardRock       = 16
    SuddenDeath    = 32
    DoubleTime     = 64
    Relax          = 128
    HalfTime       = 256
    Nightcore      = 512
    Flashlight     = 1024
    Autoplay       = 2048
    SpunOut        = 4096
    Autopilot      = 8192
    Perfect        = 16384
    Key4           = 32768
    Key5           = 65536
    Key6           = 131072
    Key7           = 262144
    Key8           = 524288
    keyMod         = 1015808
    FadeIn         = 1048576
    Random         = 2097152
    LastMod        = 4194304
    FreeModAllowed = 2077883

class Grade(str, Enum):
    XH = 0
    SH = 1
    X  = 2
    S  = 3
    A  = 4
    B  = 5
    C  = 6
    D  = 7
    F  = 8
    N  = 9

class ScoreStatus(Enum):
    Hidden    = -1
    Failed    = 0
    Exited    = 1
    Submitted = 2
    Best      = 3
    Mods      = 4
