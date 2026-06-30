
from dataclasses import dataclass
from app.common.constants import ButtonState
from app.common import officer
from app import utils
import app

@dataclass(frozen=True)
class ReplayFrame:
    delta: int
    time: int
    x: float
    y: float
    button_state: ButtonState

def validate(replay_bytes: bytes) -> tuple[bool, int, list[ReplayFrame]]:
    """Validate a replay's contents"""
    app.session.logger.debug('Validating replay...')

    frames: list[ReplayFrame] = []
    current_time: int = 0
    seed: int = 0

    try:
        # We use a custom decompression method to avoid memory
        # exhaustion attacks also known as zip bombs :))
        replay_bytes = utils.lzma_decompress(
            replay_bytes,
            memlimit=1024 * 1024 * 50,
            max_length=1024 * 1024 * 50
        )
        replay = replay_bytes.decode()
        raw_frames = replay.split(',')

        if len(raw_frames) < 100:
            # This replay is highly likely to be malformed or malicious
            # Hopefully this doesn't lead to false-positivies
            officer.call(
                f'Replay validation failed: Not enough replay frames ({len(frames)})'
            )
            return False, 0, []

        for frame in raw_frames:
            # Ignore empty frames due to trailing commas
            if not frame:
                continue

            frame_data = frame.split('|')

            if len(frame_data) != 4:
                officer.call(
                    f'Replay validation failed: Invalid frame data ({frame_data})'
                )
                return False, 0, []

            if frame_data[0] == "-12345":
                seed = int(frame_data[3])
                continue

            # Parse the frame data
            delta = int(frame_data[0])
            x = float(frame_data[1])
            y = float(frame_data[2])
            button_state = ButtonState(int(frame_data[3]))

            # Convert delta time into absolute replay time
            current_time += delta

            frame = ReplayFrame(
                delta=delta,
                time=current_time,
                x=x,
                y=y,
                button_state=button_state
            )
            frames.append(frame)
    except Exception as e:
        officer.call(
            f'Replay validation failed: {e}',
            exc_info=e
        )
        return False, 0, []

    return True, seed, frames
