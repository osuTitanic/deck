
from enum import Enum, IntEnum, IntFlag

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
