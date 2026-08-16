import re
import hashlib
import unittest

MAX_PROCESS_LINE_LENGTH = 2048 # Prevent processing long lines
MAX_PROCESS_NUM_LINES = 1000 # Prevent processing too many lines
MAX_PROCESS_LIST_SIZE = MAX_PROCESS_LINE_LENGTH * MAX_PROCESS_NUM_LINES
PROCESS_LIST_LEFT_PATTERN = re.compile(r"^([a-fA-F0-9]{32})\s+(.*)") # checked for redos

class ScoreProcess:
    """<filesize_md5> <full_path> | <process_name> (<window_title>)"""

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
    def from_line(cls, line: str):
        if line is None:
            return None

        if len(line) > MAX_PROCESS_LINE_LENGTH:
            return cls(
                full_line=line,
                md5=None,
                full_path=None,
                process_name=None,
                window_title=None
            )

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

        left, right = line.split(" | ", 1)
        match_left = PROCESS_LIST_LEFT_PATTERN.match(left)

        md5 = ""
        full_path = left
        process_name = right
        window_title = ""

        if match_left:
            md5 = match_left.group(1)
            full_path = match_left.group(2)

        if " (" in right:
            process_name, _, window_title = right.partition(" (")

            if window_title and window_title.endswith(")"):
                window_title = window_title[:-1]

        return cls(
            full_line=line,
            md5=md5,
            full_path=full_path,
            process_name=process_name,
            window_title=window_title
        )

class ScoreNetworkAdapter:
    """AABBCCDDEEFF.AABBCCDDEEFF.AABBCCDDEEFF.. (empty is fine, but normally 6 bytes uppercase)"""

    def __init__(
        self,
        physical_address: str | None
    ) -> None:
        self.physical_address = physical_address

    @classmethod
    def from_adapter_list (cls, part: str | None):
        if part is None:
            return None
        
        if part.endswith("."):
            part = part.removesuffix(".") # (osu! will send "." at the end of every adapter, including last, causing a trailing "." before split is hit)

        return [cls(physical_address=addr) for addr in part.split(".")]

class ScoreSecurityHash:
    """<osu!.exe md5>:<MAC Address[0].MAC Address[1]>:<MAC Address combined md5>:<UniqueId md5>:<UniqueId2 md5>:"""

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

    @property
    def has_adapters(self) -> bool:
        return self.network_adapters is not None and self.network_adapters_md5 is not None

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

        network_adapter_str = ""
        for adapter in self.network_adapters:
            network_adapter_str += (adapter.physical_address or "") + "."

        return ScoreSecurityHash.validate_adapters_unprocessed(network_adapter_str, self.network_adapters_md5)

    @classmethod
    def from_string(cls, security_hash_str: str):
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

class TestScoreProcess(unittest.TestCase):
    def test_from_line(self):
        tests = {
            "malicious": {
                "full_line": "a" * MAX_PROCESS_LINE_LENGTH + "b",
                "md5": None,
                "full_path": None,
                "process_name": None,
                "window_title": None
            },
            "malformed": {
                "full_line": "hi",
                "md5": None,
                "full_path": None,
                "process_name": None,
                "window_title": None
            },
            "partial": {
                "full_line": " | conhost ()",
                "md5": "",
                "full_path":  "",
                "process_name": "conhost",
                "window_title":  ""
            },
            "partial_wt": {
                "full_line": " | conhost (abc)",
                "md5":  "",
                "full_path":  "",
                "process_name": "conhost",
                "window_title": "abc"
            },
            "partial_fp": {
                "full_line": "abc | conhost (abc)",
                "md5":  "",
                "full_path": "abc",
                "process_name": "conhost",
                "window_title": "abc"
            },
            "normal": {
                "full_line": "deadbeefdeadbeefdeadbeefdeadbeef path | process name (window title)",
                "md5": "deadbeefdeadbeefdeadbeefdeadbeef",
                "full_path": "path",
                "process_name": "process name",
                "window_title": "window title"
            }
        }
        
        for key, value in tests.items():
            parsed = ScoreProcess.from_line(value["full_line"])
            self.assertEqual(parsed.md5, value["md5"], f"Expected {value['md5']}, actual: {parsed.md5} (Test: {key}, Property: md5)")
            self.assertEqual(parsed.full_path, value["full_path"], f"Expected {value['full_path']}, actual: {parsed.full_path} (Test: {key}, Property: full_path)")
            self.assertEqual(parsed.process_name, value["process_name"], f"Expected {value['process_name']}, actual: {parsed.process_name} (Test: {key}, Property: process_name)")
            self.assertEqual(parsed.window_title, value["window_title"], f"Expected {value['window_title']}, actual: {parsed.window_title} (Test: {key}, Property: window_title)")

class TestScoreNetworkAdapter(unittest.TestCase):
    def test_from_adapter_list(self):
        adapters = ScoreNetworkAdapter.from_adapter_list("AABBCCDDEE11.AABBCCDDEE22.AABBCCDDEE33.")
        self.assertEqual(len(adapters), 3)
        self.assertEqual(adapters[0].physical_address, "AABBCCDDEE11")
        self.assertEqual(adapters[1].physical_address, "AABBCCDDEE22")
        self.assertEqual(adapters[2].physical_address, "AABBCCDDEE33")

class TestScoreSecurityHash(unittest.TestCase):
    def test_validate_adapters_unprocessed(self):
        test_adapters = "AABBCCDDEE11.AABBCCDDEE22.AABBCCDDEE33."
        test_md5 = hashlib.md5(test_adapters.encode()).hexdigest()
        self.assertEqual(ScoreSecurityHash.validate_adapters_unprocessed(test_adapters, test_md5), True)

    def test_from_string(self):
        osu_exe_md5 = "f46a185e68858b722f77b05ae041e421"
        adapters = "AABBCCDDEE11.AABBCCDDEE22.AABBCCDDEE33."
        adapters_md5 = hashlib.md5(adapters.encode()).hexdigest()
        unique_id_1 = "f46a185e68858b722f77b05ae041ffff"
        unique_id_2 = "f46a185e68858b722f77b05ae0410000"

        test_string = (
            f"{osu_exe_md5}:"
            f"{adapters}:"
            f"{adapters_md5}:"
            f"{unique_id_1}:"
            f"{unique_id_2}:"
        )
        
        from_str = ScoreSecurityHash.from_string(test_string)
        self.assertEqual(from_str.osu_exe_md5, osu_exe_md5)
        self.assertEqual(isinstance(from_str.network_adapters, list), True)
        self.assertEqual(all(
            isinstance(network_adapter, ScoreNetworkAdapter) 
            for network_adapter in from_str.network_adapters),
            True
        )
        self.assertEqual(from_str.network_adapters_md5, adapters_md5)
        self.assertEqual(from_str.unique_id_md5, unique_id_1)
        self.assertEqual(from_str.unique_id2_md5, unique_id_2)

    def test_validate_adapters(self):
        osu_exe_md5 = "a"
        adapters = "AABBCCDDEE11.AABBCCDDEE22.AABBCCDDEE33."
        adapters_md5 = hashlib.md5(adapters.encode()).hexdigest()
        unique_id_1 = "b"
        unique_id_2 = "c"

        test_string = (
            f"{osu_exe_md5}:"
            f"{adapters}:"
            f"{adapters_md5}:"
            f"{unique_id_1}:"
            f"{unique_id_2}:"
        )

        from_str = ScoreSecurityHash.from_string(test_string)
        self.assertEqual(from_str.validate_adapters(), True)
        
if __name__ == "__main__":
    unittest.main()
