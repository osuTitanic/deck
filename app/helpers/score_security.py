
import hashlib
import re

MAX_PROCESS_LINE_LENGTH = 2048 # Prevent processing long lines
MAX_PROCESS_NUM_LINES = 1000 # Prevent processing too many lines
MAX_PROCESS_LIST_SIZE = MAX_PROCESS_LINE_LENGTH * MAX_PROCESS_NUM_LINES
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
class ScoreNetworkAdapter:
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
    ):
        self.osu_exe_md5 = osu_exe_md5
        self.network_adapters = network_adapters
        self.network_adapters_md5 = network_adapters_md5
        self.unique_id_md5 = unique_id_md5
        self.unique_id2_md5 = unique_id2_md5

    @staticmethod
    def validate_adapters_unprocessed(network_adapters_str: str, network_adapters_md5: str) -> bool:
        """Checks if md5(network_adapters_str) == network_adapters_md5"""
        return hashlib.md5(network_adapters_str.encode()).hexdigest() == network_adapters_md5 # we can expect the network_adapters_md5 to be lowercase coming from the client

    def validate_adapters(self) -> bool:
        """Runs a check to make sure network_adapters_md5 is a real md5 of the network_adapters"""
        if self.network_adapters is None:
            return True

        if self.network_adapters_md5 is None:
            return True

        if len(self.network_adapters) == 0:
            return True

        # We do an early check here because when we reconstruct the adapters using this value
        # we would get "runningunderwine." instead of "runningunderwine", causing the md5 to mismatch anyway.
        if self.network_adapters[0] == "runningunderwine":
            return True

        network_adapter_str = "".join(f"{adapter.physical_address  or ''}." for adapter in self.network_adapters)
        return ScoreSecurityHash.validate_adapters_unprocessed(network_adapter_str, self.network_adapters_md5)

    @classmethod
    def from_string(cls, security_hash_str: str | None) -> ScoreSecurityHash | None:
        if security_hash_str is None:
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
            network_adapters=network_adapters,
            network_adapters_md5=network_adapters_md5,
            unique_id_md5=unique_id_md5,
            unique_id2_md5=unique_id2_md5
        )
