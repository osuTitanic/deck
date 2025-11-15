
from enum import IntEnum, Enum

class CommentTarget(str, Enum):
    Replay = 'replay'
    Song   = 'song'
    Map    = 'map'

class SubmissionStatus(IntEnum):
    NotSubmitted = -1
    Pending      = 0
    Unknown      = 1
    Qualified    = 2
    Approved     = 3
    Ranked       = 4
    Loved        = 5

    @classmethod
    def from_database(cls, status: int, version: int = 0):
        if version < 4:
            return cls.from_database_legacy(status)

        return {
            -3: SubmissionStatus.NotSubmitted, # Inactive
            -2: SubmissionStatus.Pending,      # Graveyard
            -1: SubmissionStatus.Pending,      # WIP
            0:  SubmissionStatus.Pending,      # Pending
            1:  SubmissionStatus.Ranked,       # Ranked
            2:  SubmissionStatus.Approved,     # Approved
            3:  SubmissionStatus.Qualified,    # Qualified
            4:  SubmissionStatus.Loved         # Loved
        }[status]

    @classmethod
    def from_database_legacy(cls, status: int):
        return {
            -3: SubmissionStatus.NotSubmitted, # Inactive
            -2: SubmissionStatus.Pending,      # Graveyard
            -1: SubmissionStatus.Pending,      # WIP
            0:  SubmissionStatus.Pending,      # Pending
            1:  SubmissionStatus.Ranked,       # Ranked
            2:  SubmissionStatus.Approved,     # Approved
            3:  SubmissionStatus.Qualified,    # Qualified
            4:  SubmissionStatus.Approved      # Loved
        }[status]

class LegacyStatus(IntEnum):
    NotSubmitted = -1
    Pending      = 0
    Unknown      = 1
    Ranked       = 2

    @classmethod
    def from_database(cls, status: int):
        return {
            -3: LegacyStatus.NotSubmitted, # Inactive
            -2: LegacyStatus.Pending,      # Graveyard
            -1: LegacyStatus.Pending,      # WIP
            0:  LegacyStatus.Pending,      # Pending
            1:  LegacyStatus.Ranked,       # Ranked
            2:  LegacyStatus.Ranked,       # Approved
            3:  LegacyStatus.Ranked,       # Qualified
            4:  LegacyStatus.Ranked        # Loved
        }[status]
