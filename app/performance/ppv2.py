
from app.common.objects import DBScore
from app.constants import Mode

from typing import Optional

from rosu_pp_py import (
    PerformanceAttributes,
    Calculator,
    Beatmap
)

import app

# Credits: https://github.com/MaxOhn/rosu-pp-py
#          https://github.com/MaxOhn/rosu-pp

def total_hits(score: DBScore) -> int:
    if score.mode == Mode.CatchTheBeat:
        return score.n50 + score.n100 + score.n300 + score.nMiss + score.nKatu

    elif score.mode == Mode.OsuMania:
        return score.n300 + score.n100 + score.n50 + score.nGeki + score.nKatu + score.nMiss

    return score.n50 + score.n100 + score.n300 + score.nMiss

def calculate_ppv2(score: DBScore) -> Optional[PerformanceAttributes]:
    beatmap_file = app.session.storage.get_beatmap(score.beatmap_id)

    if not beatmap_file:
        return None

    bm = Beatmap(bytes=beatmap_file)

    calc = Calculator(
        mode           = score.mode,
        mods           = score.mods,
        acc            = score.acc,
        n_geki         = score.nGeki,
        n_katu         = score.nKatu,
        n300           = score.n300,
        n100           = score.n100,
        n50            = score.n50,
        n_misses       = score.nMiss,
        combo          = score.max_combo,
        passed_objects = total_hits(score)
    )

    pp = calc.performance(bm)

    return pp
