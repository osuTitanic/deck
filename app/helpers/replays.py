
from app.common.constants import ButtonState
from app.common import officer
from app import utils

from dataclasses import dataclass
from statistics import median
from math import hypot

import statistics
import app

@dataclass(frozen=True, slots=True)
class ReplayFrame:
    delta: int
    time: int
    x: float
    y: float
    button_state: ButtonState

@dataclass(frozen=True, slots=True)
class MovementSample:
    time: int
    delta: int
    distance: float
    speed: float

@dataclass(frozen=True, slots=True)
class TouchscreenAnalysis:
    movement_samples: list[MovementSample]
    teleport_samples: list[MovementSample]
    press_count: int
    presses_after_teleport: int

GAMEPLAY_BUTTONS = (
    ButtonState.Left1 | ButtonState.Right1 |
    ButtonState.Left2 | ButtonState.Right2
)

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

def detect_touchscreen_usage(frames: list[ReplayFrame], decision_threshold: float = 0.8) -> tuple[bool, float]:
    """Detect touchscreen usage from parsed replay frames"""
    movement_samples: list[MovementSample] = []
    teleport_samples: list[MovementSample] = []

    press_count = 0
    presses_after_teleport = 0
    last_teleport_time: int | None = None

    previous = frames[0]

    # We check for 3 main signals for analysis:
    # 1. Large fast cursor jumps, i.e. a movement that is considered a "teleport"
    # 2. Presses shortly after a teleport, a sign of touchscreen usage
    # 3. Very high cursor speeds, distributed across the replay (checking the 95th percentile here)

    # This method of analysis can still produce false positives, but I think its a good starting point
    # especially when only checking for high decision thresholds (0.8 by default).

    for current in frames[1:]:
        # A movement sample represents a single movement between two
        # frames, which we can analyze for speed and distance
        movement_sample = calculate_movement_sample(previous, current)

        if movement_sample is not None:
            movement_samples.append(movement_sample)

            if is_teleport_movement(movement_sample):
                teleport_samples.append(movement_sample)
                last_teleport_time = movement_sample.time

        if is_new_button_press(previous.button_state, current.button_state):
            press_count += 1

            if is_press_after_teleport(current.time, last_teleport_time):
                presses_after_teleport += 1

        previous = current

    if not movement_samples:
        # No usable movement samples were found, likely due to a malformed replay
        return False, 0.0

    if press_count < 100:
        # Not enough button presses for replay analysis to be reliable
        return False, 0.0

    analysis = TouchscreenAnalysis(
        movement_samples=movement_samples,
        teleport_samples=teleport_samples,
        press_count=press_count,
        presses_after_teleport=presses_after_teleport,
    )
    stats = build_touchscreen_stats(frames, analysis)

    teleport_ratio = stats["teleport_ratio"]
    press_teleport_ratio = stats["press_teleport_ratio"]
    p95_speed = stats["p95_speed"]

    score = calculate_touchscreen_score(
        teleport_ratio=teleport_ratio,
        press_teleport_ratio=press_teleport_ratio,
        p95_speed=p95_speed,
    )
    return score >= decision_threshold, score

def calculate_movement_sample(previous: ReplayFrame, current: ReplayFrame) -> MovementSample | None:
    delta = current.time - previous.time

    if delta <= 0:
        return None

    # Distance can be calculated using our good old friend pythagoras
    # Then we just use some simple 5th grade physics to calculate speed = distance / time
    distance = hypot(current.x - previous.x, current.y - previous.y)
    speed = distance / delta

    return MovementSample(
        time=current.time,
        delta=delta,
        distance=distance,
        speed=speed,
    )

def is_teleport_movement(
    sample: MovementSample,
    jump_distance_threshold: float = 80.0,
    speed_threshold: float = 5.0,
) -> bool:
    return (
        sample.distance >= jump_distance_threshold
        and sample.speed >= speed_threshold
    )

def is_new_button_press(previous_buttons: ButtonState, current_buttons: ButtonState) -> bool:
    previous_gameplay = int(previous_buttons & GAMEPLAY_BUTTONS)
    current_gameplay = int(current_buttons & GAMEPLAY_BUTTONS)
    return bool(current_gameplay & ~previous_gameplay)

def calculate_touchscreen_score(
    teleport_ratio: float,
    press_teleport_ratio: float,
    p95_speed: float,
) -> float:
    """Convert touchscreen detection results into a normalized score from 0.0 to 1.0"""
    teleport_score = min(teleport_ratio / 0.06, 1.0)
    press_score = min(press_teleport_ratio / 0.30, 1.0)
    speed_score = min(p95_speed / 4.0, 1.0)

    # TODO: figure out weighting for these factors, currently just a guess
    return teleport_score * 0.35 + press_score * 0.45 + speed_score * 0.20

def build_touchscreen_stats(frames: list[ReplayFrame], analysis: TouchscreenAnalysis) -> dict[str, float]:
    movement_count = len(analysis.movement_samples)
    teleport_count = len(analysis.teleport_samples)

    speeds = [sample.speed for sample in analysis.movement_samples]
    teleport_speeds = [sample.speed for sample in analysis.teleport_samples]
    teleport_ratio = teleport_count / movement_count

    press_teleport_ratio = (
        analysis.presses_after_teleport / analysis.press_count
        if analysis.press_count > 0 else 0.0
    )

    max_teleport_speed = max(teleport_speeds) if teleport_speeds else 0.0
    median_speed = median(speeds) if speeds else 0.0
    p95_speed = calculate_percentile(speeds, 0.95)

    return {
        "frame_count": len(frames),
        "teleport_ratio": teleport_ratio,
        "press_teleport_ratio": press_teleport_ratio,
        "median_speed": median_speed,
        "p95_speed": p95_speed,
        "max_teleport_speed": max_teleport_speed,
    }

def is_press_after_teleport(
    press_time: int,
    last_teleport_time: int | None,
    press_window_ms: int = 50,
) -> bool:
    if last_teleport_time is None:
        return False

    time_since_teleport = press_time - last_teleport_time
    return 0 <= time_since_teleport <= press_window_ms

def calculate_percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0

    # https://stackoverflow.com/questions/2374640/how-do-i-calculate-percentiles-with-python-numpy
    # :)
    quantiles = statistics.quantiles(values, n=100)
    index = int(percentile * 100) - 1
    return quantiles[index]
