
from datetime import datetime, timedelta
from typing import List, Callable

from app.common.database.repositories import scores, stats
from app.common.cache import leaderboards

from app.common.database.objects import DBScore
from app.common.constants import Mods

import config
import app

# I found some infos on the old achievements online:
# https://www.reddit.com/r/osugame/comments/4fnkgo/osu_achievementsmedals_thread/
# https://osu.ppy.sh/community/forums/topics/494188?n=1

class Achievement:
    def __init__(self, name: str, category: str, filename: str, condition: Callable) -> None:
        self.name      = name
        self.category  = category
        self.filename  = filename
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
    """Get an S rank on 3 different beatmaps in a row"""
    latest_scores = scores.fetch_recent(
        score.user_id,
        score.mode,
        limit=3
    )

    beatmaps = {score.beatmap_id for score in latest_scores}

    if len(beatmaps) != 3:
        # Can't be on same beatmap
        return False

    for score in latest_scores:
        if score.grade != 'S' or score.grade != 'SH':
            return False

    return True

@register(name="Most Improved", category='Hush-Hush', filename='improved.png')
def improved(score: DBScore) -> bool:
    # TODO: Not completely clear what it does
    # https://i.imgur.com/DgFGiai.png

    # if score.status != ScoreStatus.BEST:
    #     return False

    # if not score.personal_best:
    #     return False
    #     
    # previous_grade = Grade[score.personal_best.grade].value
    # new_grade      = Grade[score.grade].value

    # if previous_grade - new_grade >= 2:
    #     # We need to check that for 10-20 maps
    #     return True

    return False

@register(name='Non-stop Dancer', category='Hush-Hush', filename='dancer.png')
def dancer(score: DBScore) -> bool:
    """Pass Yoko Ishida - paraparaMAX I without No Fail"""
    if (
        score.beatmap.filename == 'Yoko Ishida - paraparaMAX I (chan) [marathon].osu' and
        score.passed and
        Mods.NoFail not in Mods(score.mods)
       ):
        return True

    return False

@register(name='Consolation Prize', category='Hush-Hush', filename='consolationprize.png')
def prize(score: DBScore) -> bool:
    """Pass the any difficulty of any ranked mapset with below 75% accuracy without no-fail and/or easy mods"""
    if score.acc > 0.75:
        return False

    if not score.beatmap.is_ranked:
        # Map is not ranked
        return False

    mods = Mods(score.mods)

    if (Mods.NoFail in mods or
        Mods.Easy   in mods):
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
    last_scores = app.session.database.session.query(DBScore) \
            .filter(DBScore.beatmap_id == score.beatmap_id) \
            .filter(DBScore.user_id == score.user_id) \
            .filter(DBScore.mode == score.mode) \
            .filter(DBScore.submitted_at > datetime.now() - timedelta(days=1)) \
            .limit(100) \
            .all()

    if len(last_scores) < 100:
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
    all_stats = app.session.database.user_stats(score.user_id)

    playcounts = [stats.playcount for stats in all_stats]

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
def osuhits_1(score: DBScore) -> bool:
    """Get a Play Count of 5,000 in osu!Standard"""
    if score.mode != 0:
        return False

    s = stats.fetch_by_mode(score.user_id, 0)

    if s.playcount < 5000:
        return False

    return True

@register(name='15,000 Plays (osu! mode)', category='Dedication', filename='plays2.png')
def osuhits_2(score: DBScore) -> bool:
    """Get a Play Count of 15,000 in osu!Standard"""
    if score.mode != 0:
        return False

    s = stats.fetch_by_mode(score.user_id, 0)

    if s.playcount < 15000:
        return False

    return True

@register(name='25,000 Plays (osu! mode)', category='Dedication', filename='plays3.png')
def osuhits_3(score: DBScore) -> bool:
    """Get a Play Count of 25,000 in osu!Standard"""
    if score.mode != 0:
        return False

    s = stats.fetch_by_mode(score.user_id, 0)

    if s.playcount < 25000:
        return False

    return True

@register(name='50,000 Plays (osu! mode)', category='Dedication', filename='plays4.png')
def osuhits_4(score: DBScore) -> bool:
    """Get a Play Count of 50,000 in osu!Standard"""
    if score.mode != 0:
        return False

    s = stats.fetch_by_mode(score.user_id, 0)

    if s.playcount < 50000:
        return False

    return True

@register(name='30,000 Drum Hits', category='Dedication', filename='taiko1.png')
def taikohits_1(score: DBScore) -> bool:
    """Hit 30,000 notes in osu!Taiko"""

    if score.mode != 1:
        return False

    s = stats.fetch_by_mode(score.user_id, 1)

    if s.playcount < 30000:
        return False

    return True

@register(name='300,000 Drum Hits', category='Dedication', filename='taiko2.png')
def taikohits_2(score: DBScore) -> bool:
    """Hit 300,000 notes in osu!Taiko"""
    if score.mode != 1:
        return False

    s = stats.fetch_by_mode(score.user_id, 1)

    if s.playcount < 300000:
        return False

    return True

@register(name='3,000,000 Drum Hits', category='Dedication', filename='taiko3.png')
def taikohits_3(score: DBScore) -> bool:
    """Hit 3,000,000 notes in osu!Taiko"""
    if score.mode != 1:
        return False

    s = stats.fetch_by_mode(score.user_id, 1)

    if s.playcount < 3000000:
        return False

    return True

@register(name='Catch 20,000 fruits', category='Dedication', filename='fruitsalad.png')
def fruitshits_1(score: DBScore) -> bool:
    """Catch 20,000 fruits in osu!CtB"""
    if score.mode != 2:
        return False

    s = stats.fetch_by_mode(score.user_id, 2)

    if s.playcount < 20000:
        return False

    return True

@register(name='Catch 200,000 fruits', category='Dedication', filename='fruitplatter.png')
def fruitshits_2(score: DBScore) -> bool:
    """Catch 200,000 fruits in osu!CtB"""
    if score.mode != 2:
        return False

    s = stats.fetch_by_mode(score.user_id, 2)

    if s.playcount < 200000:
        return False

    return True

@register(name='Catch 2,000,000 fruits', category='Dedication', filename='fruitod.png')
def fruitshits_3(score: DBScore) -> bool:
    """Catch 2,000,000 fruits in osu!CtB"""
    if score.mode != 2:
        return False

    s = stats.fetch_by_mode(score.user_id, 2)

    if s.playcount < 2000000:
        return False

    return True

@register(name='40,000 Keys', category='Dedication', filename='maniahits1.png')
def maniahits_1(score: DBScore) -> bool:
    """Hit 40,000 keys in osu!mania"""
    if score.mode != 2:
        return False

    s = stats.fetch_by_mode(score.user_id, 3)

    if s.playcount < 40000:
        return False

    return True

@register(name='400,000 Keys', category='Dedication', filename='maniahits2.png')
def maniahits_2(score: DBScore) -> bool:
    """Hit 400,000 keys in osu!mania"""
    if score.mode != 2:
        return False

    s = stats.fetch_by_mode(score.user_id, 3)

    if s.playcount < 400000:
        return False

    return True

@register(name='4,000,000 Keys', category='Dedication', filename='maniahits3.png')
def maniahits_3(score: DBScore) -> bool:
    """Hit 4,000,000 keys in osu!mania"""
    if score.mode != 2:
        return False

    s = stats.fetch_by_mode(score.user_id, 3)

    if s.playcount < 4000000:
        return False

    return True

@register(name='I can see the top', category='Skill', filename='high-ranker-1.png')
def ranking_1(score: DBScore) -> bool:
    """Reach a profile rank of at least 50,000 in any osu! mode"""
    rank = leaderboards.global_rank(score.user_id, score.mode)

    if rank > 50000:
        return False
    
    return True

@register(name='The gradual rise', category='Skill', filename='high-ranker-2.png')
def ranking_2(score: DBScore) -> bool:
    """Reach a profile rank of at least 10,000 in any osu! mode"""
    rank = leaderboards.global_rank(score.user_id, score.mode)

    if rank > 10000:
        return False
    
    return True

@register(name='Scaling up', category='Skill', filename='high-ranker-3.png')
def ranking_3(score: DBScore) -> bool:
    """Reach a profile rank of at least 5,000 in any osu! mode"""
    rank = leaderboards.global_rank(score.user_id, score.mode)

    if rank > 5000:
        return False
    
    return True

@register(name='Approaching the summit', category='Skill', filename='high-ranker-4.png')
def ranking_3(score: DBScore) -> bool:
    """Reach a profile rank of at least 1,000 in any osu! mode"""
    rank = leaderboards.global_rank(score.user_id, score.mode)

    if rank > 1000:
        return False
    
    return True

# TODO
# 'Video Game Pack vol.1'  'Beatmap Packs' 'gamer1.png'
# 'Video Game Pack vol.2'  'Beatmap Packs' 'gamer2.png'
# 'Video Game Pack vol.3'  'Beatmap Packs' 'gamer3.png'
# 'Video Game Pack vol.4'  'Beatmap Packs' 'gamer4.png'
# 'Anime Pack vol.1'       'Beatmap Packs' 'anime1.png'
# 'Anime Pack vol.2'       'Beatmap Packs' 'anime2.png'
# 'Anime Pack vol.3'       'Beatmap Packs' 'anime3.png'
# 'Anime Pack vol.4'       'Beatmap Packs' 'anime4.png'
# 'Internet! Pack vol.1'   'Beatmap Packs' 'lulz1.png'
# 'Internet! Pack vol.2'   'Beatmap Packs' 'lulz2.png'
# 'Internet! Pack vol.3'   'Beatmap Packs' 'lulz3.png'
# 'Internet! Pack vol.4'   'Beatmap Packs' 'lulz4.png'
# 'Rythm Game Pack vol.1'  'Beatmap Packs' 'rythm1.png'
# 'Rythm Game Pack vol.2'  'Beatmap Packs' 'rythm2.png'
# 'Rythm Game Pack vol.3'  'Beatmap Packs' 'rythm3.png'
# 'Rythm Game Pack vol.4'  'Beatmap Packs' 'rythm4.png'

def get_by_name(name: str):
    for achievement in achievements:
        if achievement.name == name:
            return achievement
    return None

def check(score: DBScore, ignore_list: List[Achievement] = []) -> List[Achievement]:
    new_achievements = []

    for achievement in achievements:
        if achievement.filename in ignore_list:
            continue

        if achievement.check(score):
            new_achievements.append(achievement)

            app.session.logger.info(f'Player {score.user} unlocked achievement: {achievement.name}')
            app.highlights.submit(
                score.user_id,
                score.mode,
                '{}' + f' unlocked an achievement: {achievement.name}',
                (score.user.name, f'http://{config.DOMAIN_NAME}/u/{score.user_id}')
            )

    return new_achievements
