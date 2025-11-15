
from enum import IntFlag, IntEnum, Enum

class CommentTarget(str, Enum):
    Replay = 'replay'
    Song   = 'song'
    Map    = 'map'

class BadFlags(IntFlag):
	Clean                       = 0
	# TODO: ?? 					= 1
	SpeedHackDetected           = 2
	IncorrectModValue           = 4
	MultipleOsuClients          = 8
	ChecksumFailure             = 16
	FlashlightChecksumIncorrect = 32
	OsuExecutableChecksum       = 64
	MissingProcessesInList      = 128
	FlashLightImageHack         = 256
	SpinnerHack                 = 512
	TransparentWindow           = 1024
	FastPress                   = 2048
	RawMouseDiscrepancy			= 4096
	RawKeyboardDiscrepancy		= 8192

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
