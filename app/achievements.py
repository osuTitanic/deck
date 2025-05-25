
from concurrent.futures import Future, TimeoutError
from datetime import datetime, timedelta
from typing import List, Callable, Tuple
from sqlalchemy.orm import Session

from app.common.database.objects import DBScore, DBBeatmap
from app.common.database.repositories import scores
from app.common.constants import ScoreStatus, Grade
from app.common.cache import leaderboards
from app.common.constants import Mods

import config
import app

# I found some infos on the old achievements online:
# https://www.reddit.com/r/osugame/comments/4fnkgo/osu_achievementsmedals_thread/
# https://osu.ppy.sh/community/forums/topics/494188?n=1

class Achievement:
    def __init__(self, name: str, category: str, filename: str, condition: Callable) -> None:
        self.name = name
        self.category = category
        self.filename = filename
        self.condition = condition

    def __repr__(self) -> str:
        return f'[{self.category}] {self.name}'

    def check(self, score) -> bool:
        return self.condition(score)

achievements: List[Achievement] = []

def register(name: str, category: str, filename: str) -> Callable:
    """Register a achievement"""

    def wrapper(condition: Callable):
        a = Achievement(
            name, category, filename, condition
        )
        achievements.append(a)

        return a

    return wrapper

def check_pack(score: DBScore, beatmapset_ids: List[int]) -> bool:
    if score.beatmap.set_id not in beatmapset_ids:
        # Score was not set inside this pack
        return False

    with app.session.database.managed_session() as session:
        for set_id in beatmapset_ids:
            result = session.query(DBScore) \
                .join(DBBeatmap) \
                .filter(DBBeatmap.set_id == set_id) \
                .filter(DBScore.user_id == score.user_id) \
                .filter(DBScore.status_pp == 3) \
                .filter(DBScore.hidden == False) \
                .first()

            if not result:
                # User has not completed this beatmap
                return False

    return True

@register(name='500 Combo  (any song)', category='Skill', filename='combo500.png')
def combo500(score: DBScore) -> bool:
    """Get a 500 combo on any map """
    if score.max_combo >= 500:
        return True

    return False

@register(name='750 Combo  (any song)', category='Skill', filename='combo750.png')
def combo750(score: DBScore) -> bool:
    """Get a 750 combo on any map"""
    if score.max_combo >= 750:
        return True

    return False

@register(name='1000 Combo  (any song)', category='Skill', filename='combo1000.png')
def combo1000(score: DBScore) -> bool:
    """Get a 1000 combo on any map"""
    if score.max_combo >= 1000:
        return True

    return False

@register(name='2000 Combo  (any song)', category='Skill', filename='combo2000.png')
def combo2000(score: DBScore) -> bool:
    """Get a 2000 combo on any map"""
    if score.max_combo >= 2000:
        return True

    return False

@register(name="Don't let the bunny distract you!", category='Hush-Hush', filename='bunny.png')
def bunny(score: DBScore) -> bool:
    """Get a 371 out of 371 combo in the normal or a 447 out of 447 combo in the hard of the beatmap "Chatmonchy - Make Up! Make Up!" by peppy"""
    if score.beatmap.filename.startswith('Chatmonchy - Make Up! Make Up! (peppy)'):
        if score.perfect:
            return True

    return False

@register(name="S-Ranker", category='Hush-Hush', filename='s-ranker.png')
def sranker(score: DBScore) -> bool:
    """Get an S rank on 5 different beatmaps in a row"""
    latest_scores = scores.fetch_recent(
        score.user_id,
        score.mode,
        limit=5
    )

    beatmaps = {score.beatmap_id for score in latest_scores}

    if len(beatmaps) != 5:
        # Can't be on same beatmap
        return False

    for score in latest_scores:
        if Grade[score.grade] > Grade.S:
            return False

    return True

@register(name="Most Improved", category='Hush-Hush', filename='improved.png')
def improved(score: DBScore) -> bool:
    """Set a D Rank then A rank (or higher), in the last day"""
    if score.status_pp != ScoreStatus.Best:
        return False

    with app.session.database.managed_session() as session:
        # Check if player has set a D Rank in the last 24 hours
        result = session.query(DBScore) \
            .filter(
                DBScore.submitted_at > (
                    datetime.now() - timedelta(days=1)
                )
            ) \
            .filter(DBScore.beatmap_id == score.beatmap_id) \
            .filter(DBScore.user_id == score.user_id) \
            .filter(DBScore.grade == 'D') \
            .first()

    if not result:
        return False

    if Grade[score.grade] <= Grade.A:
        return True

    return False

@register(name='Non-stop Dancer', category='Hush-Hush', filename='dancer.png')
def dancer(score: DBScore) -> bool:
    """Pass Yoko Ishida - paraparaMAX I without No Fail"""
    if (
        score.beatmap.filename == 'Yoko Ishida - paraparaMAX I (chan) [marathon].osu'
        and Mods.NoFail not in Mods(score.mods)
    ):
        return True

    return False

@register(name='Consolation Prize', category='Hush-Hush', filename='consolationprize.png')
def prize(score: DBScore) -> bool:
    """Pass the any difficulty of any ranked mapset with below 75% accuracy without no-fail and/or easy mods"""
    if Grade[score.grade] != Grade.D:
        return False

    mods = Mods(score.mods)

    if (Mods.Easy in mods) or (Mods.NoFail in mods):
        return False

    return True

@register(name='Challenge Accepted', category='Hush-Hush', filename='challengeaccepted.png')
def approved(score: DBScore) -> bool:
    """Complete an Approved map"""
    if score.beatmap.approved:
        return True

    return False

@register(name='Stumbler', category='Hush-Hush', filename='stumbler.png')
def stumbler(score: DBScore) -> bool:
    """Full Combo a map with less than 85% accuracy"""
    if not score.perfect:
        return False

    if score.acc > 0.85:
        return False

    return True

@register(name='Jackpot', category='Hush-Hush', filename='jackpot.png')
def jackpot(score: DBScore) -> bool:
    """Complete a map with a score of at least 6 recurring numbers (ie. 222,222 or 6,666,666)"""
    tscore = str(score.total_score)
    num_list = [*tscore]

    for num in num_list:
        if num_list.count(num) >= 6:
            return True

    return False

@register(name='Quick Draw', category='Hush-Hush', filename='quickdraw.png')
def quickdraw(score: DBScore) -> bool:
    """Be the first person to pass a ranked or qualified map"""
    if not score.beatmap.is_ranked:
        return False

    all_scores = scores.fetch_range_scores(score.beatmap_id, score.mode)

    if len(all_scores) > 1:
        return False

    return True

@register(name='Obsessed', category='Hush-Hush', filename='obsessed.png')
def obsessed(score: DBScore) -> bool:
    """Play the same map over 100 times in a day, retries included"""
    with app.session.database.managed_session() as session:
        score_count = session.query(DBScore) \
            .filter(DBScore.beatmap_id == score.beatmap_id) \
            .filter(DBScore.user_id == score.user_id) \
            .filter(DBScore.mode == score.mode) \
            .filter(DBScore.submitted_at > datetime.now() - timedelta(days=1)) \
            .limit(100) \
            .count()

    if score_count < 100:
        return False

    return True

@register(name='Nonstop', category='Hush-Hush', filename='nonstop.png')
def nonstop(score: DBScore) -> bool:
    """Get a Max Combo on a map with over 10 minutes of drain time"""
    if score.max_combo < score.beatmap.max_combo:
        return False

    if score.beatmap.total_length < 600:
        return False

    return True

@register(name='Jack of All Trades', category='Hush-Hush', filename='jack.png')
def allmodes(score: DBScore) -> bool:
    """Reach a play count of at least 5,000 in all osu!Standard, osu!Taiko, osu!CtB and osu!Mania"""

    playcounts = [stats.playcount for stats in score.user.stats]

    for plays in playcounts:
        if plays < 5000:
            return False

    return True

@register(name='A meganekko approaches', category='Hush-Hush', filename='meganekko.png')
def nekko(score: DBScore) -> bool:
    """Meet Maria, the osu!mania mascot. Finish an osu!mania map with at least a 100 combo"""
    if score.mode != 3:
        return False

    if score.max_combo < 100:
        return False

    return True

@register(name='5,000 Plays (osu! mode)', category='Dedication', filename='plays1.png')
def osuplays_1(score: DBScore) -> bool:
    """Get a Play Count of 5,000 in osu!Standard"""
    if score.mode != 0:
        return False

    s = score.user.stats[0]

    if s.playcount < 5000:
        return False

    return True

@register(name='15,000 Plays (osu! mode)', category='Dedication', filename='plays2.png')
def osuplays_2(score: DBScore) -> bool:
    """Get a Play Count of 15,000 in osu!Standard"""
    if score.mode != 0:
        return False

    s = score.user.stats[0]

    if s.playcount < 15000:
        return False

    return True

@register(name='25,000 Plays (osu! mode)', category='Dedication', filename='plays3.png')
def osuplays_3(score: DBScore) -> bool:
    """Get a Play Count of 25,000 in osu!Standard"""
    if score.mode != 0:
        return False

    s = score.user.stats[0]

    if s.playcount < 25000:
        return False

    return True

@register(name='50,000 Plays (osu! mode)', category='Dedication', filename='plays4.png')
def osuplays_4(score: DBScore) -> bool:
    """Get a Play Count of 50,000 in osu!Standard"""
    if score.mode != 0:
        return False

    s = score.user.stats[0]

    if s.playcount < 50000:
        return False

    return True

@register(name='30,000 Drum Hits', category='Dedication', filename='taiko1.png')
def taikohits_1(score: DBScore) -> bool:
    """Hit 30,000 notes in osu!Taiko"""

    if score.mode != 1:
        return False

    s = score.user.stats[1]

    if s.total_hits < 30000:
        return False

    return True

@register(name='300,000 Drum Hits', category='Dedication', filename='taiko2.png')
def taikohits_2(score: DBScore) -> bool:
    """Hit 300,000 notes in osu!Taiko"""
    if score.mode != 1:
        return False

    s = score.user.stats[1]

    if s.total_hits < 300000:
        return False

    return True

@register(name='3,000,000 Drum Hits', category='Dedication', filename='taiko3.png')
def taikohits_3(score: DBScore) -> bool:
    """Hit 3,000,000 notes in osu!Taiko"""
    if score.mode != 1:
        return False

    s = score.user.stats[1]

    if s.total_hits < 3000000:
        return False

    return True

@register(name='Catch 20,000 fruits', category='Dedication', filename='fruitsalad.png')
def fruitshits_1(score: DBScore) -> bool:
    """Catch 20,000 fruits in osu!CtB"""
    if score.mode != 2:
        return False

    s = score.user.stats[2]

    if s.total_hits < 20000:
        return False

    return True

@register(name='Catch 200,000 fruits', category='Dedication', filename='fruitplatter.png')
def fruitshits_2(score: DBScore) -> bool:
    """Catch 200,000 fruits in osu!CtB"""
    if score.mode != 2:
        return False

    s = score.user.stats[2]

    if s.total_hits < 200000:
        return False

    return True

@register(name='Catch 2,000,000 fruits', category='Dedication', filename='fruitod.png')
def fruitshits_3(score: DBScore) -> bool:
    """Catch 2,000,000 fruits in osu!CtB"""
    if score.mode != 2:
        return False

    s = score.user.stats[2]

    if s.total_hits < 2000000:
        return False

    return True

@register(name='40,000 Keys', category='Dedication', filename='maniahits1.png')
def maniahits_1(score: DBScore) -> bool:
    """Hit 40,000 keys in osu!mania"""
    if score.mode != 2:
        return False

    s = score.user.stats[3]

    if s.total_hits < 40000:
        return False

    return True

@register(name='400,000 Keys', category='Dedication', filename='maniahits2.png')
def maniahits_2(score: DBScore) -> bool:
    """Hit 400,000 keys in osu!mania"""
    if score.mode != 2:
        return False

    s = score.user.stats[3]

    if s.total_hits < 400000:
        return False

    return True

@register(name='4,000,000 Keys', category='Dedication', filename='maniahits3.png')
def maniahits_3(score: DBScore) -> bool:
    """Hit 4,000,000 keys in osu!mania"""
    if score.mode != 2:
        return False

    s = score.user.stats[3]

    if s.total_hits < 4000000:
        return False

    return True

@register(name='I can see the top', category='Skill', filename='high-ranker-1.png')
def ranking_1(score: DBScore) -> bool:
    """Reach a profile rank of at least 500 in any osu! mode"""
    rank = leaderboards.global_rank(score.user_id, score.mode)

    # NOTE: Used to be 50,000
    if rank > 500:
        return False

    return True

@register(name='The gradual rise', category='Skill', filename='high-ranker-2.png')
def ranking_2(score: DBScore) -> bool:
    """Reach a profile rank of at least 100 in any osu! mode"""
    rank = leaderboards.global_rank(score.user_id, score.mode)

    # NOTE: Used to be 10,000
    if rank > 100:
        return False

    return True

@register(name='Scaling up', category='Skill', filename='high-ranker-3.png')
def ranking_3(score: DBScore) -> bool:
    """Reach a profile rank of at least 50 in any osu! mode"""
    rank = leaderboards.global_rank(score.user_id, score.mode)

    # NOTE: Used to be 5,000
    if rank > 50:
        return False

    return True

@register(name='Approaching the summit', category='Skill', filename='high-ranker-4.png')
def ranking_3(score: DBScore) -> bool:
    """Reach a profile rank of at least 15 in any osu! mode"""
    rank = leaderboards.global_rank(score.user_id, score.mode)

    # NOTE: Used to be 1,000
    if rank > 10:
        return False

    return True

@register(name='Video Game Pack vol.1', category='Beatmap Packs', filename='gamer1.png')
def video_game_1(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            1635,
            1211,
            1231,
            1281,
            1092,
            312,
            633,
            688,
            704,
            154,
            125,
            92,
            25
        ]
    )

@register(name='Video Game Pack vol.2', category='Beatmap Packs', filename='gamer2.png')
def video_game_2(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            1044,
            1123,
            1367,
            1525,
            1818,
            2008,
            2128,
            2147,
            2404,
            2420,
            243,
            2619,
            628
        ]
    )

@register(name='Video Game Pack vol.3', category='Beatmap Packs', filename='gamer3.png')
def video_game_3(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            1890,
            2085,
            2490,
            2983,
            3150,
            3221,
            3384,
            3511,
            3613,
            4033,
            4299,
            4305,
            4629
        ]
    )

@register(name='Video Game Pack vol.4', category='Beatmap Packs', filename='gamer4.png')
def video_game_4(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            10104,
            10880,
            13489,
            14205,
            14458,
            16669,
            17373,
            21836,
            23073,
            7077,
            9580,
            9668,
            9854
        ]
    )

@register(name='Anime Pack vol.1', category='Beatmap Packs', filename='anime1.png')
def anime_1(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            1005,
            1377,
            1414,
            1464,
            147,
            1806,
            301,
            35,
            442,
            511,
            584,
            842,
            897
        ]
    )

@register(name='Anime Pack vol.2', category='Beatmap Packs', filename='anime2.png')
def anime_2(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            150,
            162,
            205,
            212,
            2207,
            2267,
            2329,
            2425,
            302,
            496,
            521,
            86,
            956
        ]
    )

@register(name='Anime Pack vol.3', category='Beatmap Packs', filename='anime3.png')
def anime_3(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            2618,
            3030,
            4851,
            4994,
            5010,
            5235,
            5410,
            5480,
            5963,
            6037,
            6257,
            6535,
            6557
        ]
    )

@register(name='Anime Pack vol.4', category='Beatmap Packs', filename='anime4.png')
def anime_4(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            12982,
            13036,
            13673,
            14256,
            14694,
            16252,
            21197,
            516,
            5438,
            6301,
            8422,
            8829,
            9556
        ]
    )

@register(name='Internet! Pack vol.1', category='Beatmap Packs', filename='lulz1.png')
def internet_1(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            66,
            132,
            140,
            235,
            303,
            339,
            455,
            664,
            812,
            977,
            1018,
            1287
        ]
    )

@register(name='Internet! Pack vol.2', category='Beatmap Packs', filename='lulz2.png')
def internet_2(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            203,
            917,
            1573,
            1628,
            1785,
            2103,
            2569,
            3196,
            3219,
            3545,
            3621,
            4535,
            5014
        ]
    )

@register(name='Internet! Pack vol.3', category='Beatmap Packs', filename='lulz3.png')
def internet_3(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            1839,
            3337,
            3367,
            3688,
            5703,
            5709,
            5823,
            6526,
            6626,
            7506,
            7507,
            8034,
            8690
        ]
    )

@register(name='Internet! Pack vol.4', category='Beatmap Packs', filename='lulz4.png')
def internet_4(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            11443,
            12033,
            12155,
            13885,
            14391,
            14579,
            14672,
            15157,
            15628,
            15942,
            17145,
            17217,
            17724
        ]
    )

@register(name='Rhythm Game Pack vol.1', category='Beatmap Packs', filename='rhythm1.png')
def rhythm_game_1(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            1452,
            1450,
            1078,
            1201,
            1300,
            1317,
            1338,
            210,
            296,
            540,
            564,
            74,
            96
        ]
    )

@register(name='Rhythm Game Pack vol.2', category='Beatmap Packs', filename='rhythm2.png')
def rhythm_game_2(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            1207,
            1567,
            2534,
            3302,
            3435,
            3499,
            4887,
            5087,
            5177,
            5275,
            5321,
            5349,
            5577
        ]
    )

@register(name='Rhythm Game Pack vol.3', category='Beatmap Packs', filename='rhythm3.png')
def rhythm_game_3(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            1206,
            4357,
            4617,
            4772,
            4954,
            5180,
            5672,
            5696,
            6598,
            7094,
            7237,
            7612,
            7983
        ]
    )

@register(name='Rhythm Game Pack vol.4', category='Beatmap Packs', filename='rhythm4.png')
def rhythm_game_4(score: DBScore) -> bool:
    return check_pack(
        score,
        beatmapset_ids=[
            10842,
            11135,
            11488,
            12052,
            12190,
            12710,
            13249,
            14572,
            14778,
            15241,
            18492,
            19809,
            22401
        ]
    )

def check(score: DBScore, session: Session, ignore_list: List[Achievement] = []) -> List[Achievement]:
    app.session.logger.debug('Checking for new achievements...')

    results: List[Tuple[Future, Achievement]] = []
    new_achievements: List[Achievement] = []

    score.user.stats.sort(
        key=lambda x: x.mode
    )

    for achievement in achievements:
        if achievement.filename in ignore_list:
            continue

        results.append((
            app.session.achievement_executor.submit(
                achievement.check,
                score
            ),
            achievement
        ))

    for future, achievement in results:
        try:
            if not future.result(timeout=15):
                # Achievement was not unlocked
                continue

            new_achievements.append(achievement)

            app.session.logger.info(
                f'Player {score.user} unlocked achievement: {achievement.name}'
            )
            app.highlights.submit(
                score.user_id,
                score.mode,
                session,
                '{}' + f' unlocked an achievement: {achievement.name}',
                (score.user.name, f'http://osu.{config.DOMAIN_NAME}/u/{score.user_id}')
            )
        except TimeoutError as e:
            app.session.logger.error(
                f'Achievement check for "{future.__class__.__name__}" timed out: {e}',
                exc_info=e
            )
            continue

    return new_achievements
