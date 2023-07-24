
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy     import create_engine, func, or_
from sqlalchemy.exc import ResourceClosedError

from app.achievements import Achievement
from app.constants import DisplayMode

from typing import Optional, Generator, List
from threading import Timer, Thread
from datetime import datetime

from .objects import (
    DBReplayHistory,
    DBRelationship,
    DBRankHistory,
    DBPlayHistory,
    DBAchievement,
    DBBeatmapset,
    DBScreenshot,
    DBFavourite,
    DBActivity,
    DBComment,
    DBBeatmap,
    DBRating,
    DBScore,
    DBStats,
    DBUser,
    DBPlay,
    DBLog,
    Base
)

import traceback
import logging
import app

class Postgres:
    def __init__(self, username: str, password: str, host: str, port: int) -> None:
        self.engine = create_engine(
            f'postgresql://{username}:{password}@{host}:{port}/{username}', 
            echo=False
        )

        self.logger = logging.getLogger('database')

        Base.metadata.create_all(bind=self.engine)

        self.session_factory = scoped_session(
            sessionmaker(self.engine, expire_on_commit=False, autoflush=True)
        )
    
    @property
    def session(self) -> Session:
        for session in self.create_session():
            return session

    def create_session(self) -> Generator:
        session = self.session_factory()
        try:
            yield session
        except Exception as e:
            traceback.print_exc()
            self.logger.critical(f'Transaction failed: "{e}". Performing rollback...')
            session.rollback()
        finally:
            Timer(
                interval=60,
                function=self.close_session,
                args=[session]
            ).start()

    def close_session(self, session: Session) -> None:
        try:
            session.close()
        except AttributeError:
            pass
        except ResourceClosedError:
            pass
        except Exception as exc:
            self.logger.error(f'Failed to close session: {exc}')

    def user_by_name(self, name: str) -> Optional[DBUser]:
        return self.session.query(DBUser) \
                .filter(DBUser.name == name) \
                .first()
    
    def user_by_id(self, id: int) -> Optional[DBUser]:
        return self.session.query(DBUser) \
                .filter(DBUser.id == id) \
                .first()

    def beatmap_by_id(self, id: int) -> Optional[DBBeatmap]:
        return self.session.query(DBBeatmap) \
                .filter(DBBeatmap.id == id) \
                .first()

    def beatmap_by_file(self, filename: str) -> Optional[DBBeatmap]:
        return self.session.query(DBBeatmap) \
                .filter(DBBeatmap.filename == filename) \
                .first()

    def beatmap_by_checksum(self, md5: str) -> Optional[DBBeatmap]:
        return self.session.query(DBBeatmap) \
                .filter(DBBeatmap.md5 == md5) \
                .first()

    def set_by_id(self, id: int) -> Optional[DBBeatmapset]:
        return self.session.query(DBBeatmapset) \
                .filter(DBBeatmapset.id == id) \
                .first()

    def comments(self, id: int, type: str) -> List[DBComment]:
        return self.session.query(DBComment) \
                .filter(DBComment.target_id == id) \
                .filter(DBComment.target_type == type) \
                .order_by(DBComment.time.asc()) \
                .all()

    def user_stats(self, user_id: int) -> List[DBStats]:
        return self.session.query(DBStats) \
                .filter(DBStats.user_id == user_id) \
                .all()

    def user_stats_by_mode(self, user_id: int, mode: int):
        return self.session.query(DBStats) \
                .filter(DBStats.user_id == user_id) \
                .filter(DBStats.mode == mode) \
                .first()

    def ratings(self, beatmap_hash) -> List[int]:
        return [
            rating[0]
            for rating in self.session.query(DBRating.rating) \
                .filter(DBRating.map_checksum == beatmap_hash) \
                .all()
        ]

    def rating(self, beatmap_hash: str, user_id: int) -> Optional[DBRating]:
        result = self.session.query(DBRating.rating) \
            .filter(DBRating.map_checksum == beatmap_hash) \
            .filter(DBRating.user_id == user_id) \
            .first()
        
        return result[0] if result else None

    def favourites(self, user_id: int) -> List[DBFavourite]:
        return self.session.query(DBFavourite) \
                .filter(DBFavourite.user_id == user_id) \
                .all()
    
    def score(self, id: int) -> Optional[DBScore]:
        return self.session.query(DBScore) \
                .filter(DBScore.id == id) \
                .first()

    def score_by_checksum(self, replay_md5: str) -> Optional[DBScore]:
        return self.session.query(DBScore) \
                           .filter(DBScore.replay_md5 == replay_md5) \
                           .first()

    def score_count(self, user_id: int, mode: int) -> int:
        return self.session.query(DBScore) \
                           .filter(DBScore.user_id == user_id) \
                           .filter(DBScore.mode == mode) \
                           .filter(DBScore.status == 3) \
                           .count()

    def top_scores(self, user_id: int, mode: int, exclude_approved: bool = False) -> List[DBScore]:
        query = self.session.query(DBScore) \
                        .filter(DBScore.user_id == user_id) \
                        .filter(DBScore.mode == mode) \
                        .filter(DBScore.status == 3)

        if exclude_approved:
            query = query.filter(DBBeatmap.status == 1) \
                         .join(DBScore.beatmap)

        return query.order_by(DBScore.pp.desc()) \
                    .limit(100) \
                    .offset(0) \
                    .all()

    def personal_best(
        self,
        beatmap_id: int,
        user_id: int,
        mode: int,
        mods: Optional[int] = None
    ) -> Optional[DBScore]:
        if mods == None:
            return self.session.query(DBScore) \
                    .filter(DBScore.beatmap_id == beatmap_id) \
                    .filter(DBScore.user_id == user_id) \
                    .filter(DBScore.mode == mode) \
                    .filter(DBScore.status == 3) \
                    .first()
        
        return self.session.query(DBScore) \
                .filter(DBScore.beatmap_id == beatmap_id) \
                .filter(DBScore.user_id == user_id) \
                .filter(DBScore.mode == mode) \
                .filter(or_(DBScore.status == 3, DBScore.status == 4)) \
                .filter(DBScore.mods == mods) \
                .first()

    def range_scores(
        self,
        beatmap_id: int,
        mode: int,
        offset: int = 0,
        limit: int = 5
    ) -> List[DBScore]:

        return self.session.query(DBScore) \
            .filter(DBScore.beatmap_id == beatmap_id) \
            .filter(DBScore.mode == mode) \
            .filter(DBScore.status == 3) \
            .order_by(DBScore.total_score.desc()) \
            .offset(offset) \
            .limit(limit) \
            .all()

    def range_scores_country(
        self,
        beatmap_id: int,
        mode: int,
        country: str,
        limit: int = 5
    ) -> List[DBScore]:
        return self.session.query(DBScore) \
                .filter(DBScore.beatmap_id == beatmap_id) \
                .filter(DBScore.mode == mode) \
                .filter(DBScore.status == 3) \
                .filter(DBUser.country == country) \
                .join(DBScore.user) \
                .limit(limit) \
                .all()

    def range_scores_friends(
        self,
        beatmap_id: int,
        mode: int,
        friends: List[int],
        limit: int = 5
    ):
        return self.session.query(DBScore) \
                .filter(DBScore.beatmap_id == beatmap_id) \
                .filter(DBScore.mode == mode) \
                .filter(DBScore.status == 3) \
                .filter(DBScore.user_id.in_(friends)) \
                .limit(limit) \
                .all()

    def range_scores_mods(
        self,
        beatmap_id: int,
        mode: int,
        mods: int,
        limit: int = 5
    ) -> List[DBScore]:
        return self.session.query(DBScore) \
            .filter(DBScore.beatmap_id == beatmap_id) \
            .filter(DBScore.mode == mode) \
            .filter(or_(DBScore.status == 3, DBScore.status == 4)) \
            .filter(DBScore.mods == mods) \
            .order_by(DBScore.total_score.desc()) \
            .limit(limit) \
            .all()

    def score_index(
        self, 
        user_id: int, 
        beatmap_id: int,
        mode: int,
        mods: Optional[int] = None,
        friends: Optional[List[int]] = None,
        country: Optional[str] = None
    ) -> int:
        instance = self.session

        query = instance.query(DBScore.user_id, DBScore.mods, func.rank() \
                    .over(
                        order_by=DBScore.total_score.desc()
                    ).label('rank')
                ) \
                .filter(DBScore.beatmap_id == beatmap_id) \
                .filter(DBScore.mode == mode) \
                .order_by(DBScore.total_score.desc())

        if mods != None:
            query = query.filter(DBScore.mods == mods) \
                         .filter(or_(DBScore.status == 3, DBScore.status == 4))

        if country != None:
            query = query.join(DBScore.user) \
                         .filter(DBScore.status == 3) \
                         .filter(DBUser.country == country) \

        if friends != None:
            query = query.filter(DBScore.status == 3) \
                         .filter(
                            or_(
                                DBScore.user_id.in_(friends),
                                DBScore.user_id == user_id
                            )
                         )

        subquery = query.subquery()

        if not (result := instance.query(subquery.c.rank) \
                                  .filter(subquery.c.user_id == user_id) \
                                  .first()):
            return -1

        return result[-1]

    def score_index_by_id(
        self,
        score_id: int,
        beatmap_id: int,
        mode: int,
        mods: Optional[int] = None
    ) -> int:
        instance = self.session

        query = instance.query(DBScore.id, DBScore.mods, func.rank() \
                    .over(
                        order_by=DBScore.total_score.desc()
                    ).label('rank')
                ) \
                .filter(DBScore.beatmap_id == beatmap_id) \
                .filter(DBScore.mode == mode) \
                .order_by(DBScore.total_score.desc())

        if mods != None:
            query = query.filter(DBScore.mods == mods) \
                         .filter(or_(DBScore.status == 3, DBScore.status == 4))

        subquery = query.subquery()

        if not (result := instance.query(subquery.c.rank) \
                                  .filter(subquery.c.id == score_id) \
                                  .first()):
            return -1

        return result[-1]

    def score_above(self, beatmap_id: int, mode: int, total_score: int) -> Optional[DBScore]:
        return self.session.query(DBScore) \
                           .filter(DBScore.beatmap_id == beatmap_id) \
                           .filter(DBScore.mode == mode) \
                           .filter(DBScore.total_score > total_score) \
                           .order_by(DBScore.total_score.asc()) \
                           .first()

    def recent_scores(self, user_id: int, mode: int, limit: int = 3) -> List[DBScore]:
        return self.session.query(DBScore) \
                    .filter(DBScore.user_id == user_id) \
                    .filter(DBScore.mode == mode) \
                    .order_by(DBScore.id.desc()) \
                    .limit(limit) \
                    .all()

    def relationships(self, user_id: int) -> List[DBRelationship]:
        return self.session.query(DBRelationship) \
                .filter(DBRelationship.user_id == user_id) \
                .all()

    def achievements(self, user_id: int) -> List[DBAchievement]:
        return self.session.query(DBAchievement) \
                .filter(DBAchievement.user_id == user_id) \
                .all()

    def search(
        self, 
        query_string: str, 
        user_id: int, 
        display_mode = DisplayMode.All
    ) -> List[DBBeatmapset]:
        query = self.session.query(DBBeatmapset)

        if display_mode == DisplayMode.Ranked:
            query = query.filter(DBBeatmapset.status == 1)
        
        elif display_mode == DisplayMode.Pending:
            query = query.filter(DBBeatmapset.status == 0)

        elif display_mode == DisplayMode.Graveyard:
            query = query.filter(DBBeatmapset.status == -1)
        
        elif display_mode == DisplayMode.Played:
            query = query.join(DBPlay) \
                         .filter(DBPlay.user_id == user_id)

        if query_string == 'Newest':
            query = query.order_by(DBBeatmapset.created_at.desc())
        
        elif query_string == 'Top Rated':
            query = query.join(DBRating) \
                         .group_by(DBBeatmapset.id) \
                         .order_by(func.avg(DBRating.rating).desc())

        elif query_string == 'Most Played':
            query = query.join(DBBeatmap) \
                         .group_by(DBBeatmapset.id) \
                         .order_by(func.sum(DBBeatmap.playcount).desc())

        else:
            query = query.filter(DBBeatmapset.query_string.like('%' + query_string.lower() + '%'))

        return query.limit(100).all()

    def add_achievements(self, achievements: List[Achievement], user_id: int):
        instance = self.session

        for a in achievements:
            instance.add(
                DBAchievement(
                    user_id,
                    a.name,
                    a.category,
                    a.filename
                )
            )

        instance.commit()

    def submit_favourite(self, user_id: int, set_id: int):
        instance = self.session

        # Check if favourite was already set
        if instance.query(DBFavourite.user_id) \
            .filter(DBFavourite.user_id == user_id) \
            .filter(DBFavourite.set_id == set_id) \
            .first():
            return

        instance.add(
            DBFavourite(
                user_id,
                set_id
            )
        )
        instance.commit()

    def submit_rating(self, user_id: int, beatmap_hash: str, set_id: int, rating: int):
        instance = self.session
        instance.add(
            DBRating(
                user_id,
                set_id,
                beatmap_hash,
                rating
            )
        )
        instance.commit()

    def submit_log(self, message: str, level: str, log_type: str):
        instance = self.session
        instance.add(
            DBLog(
                message,
                level,
                log_type
            )
        )
        instance.commit()

    def submit_comment(
        self,
        target_id: int,
        target: str,
        user_id: int,
        time: int,
        content: str,
        comment_format: str,
        playmode: int,
        color: str
    ):
        instance = self.session
        instance.add(
            DBComment(
                target_id,
                target,
                user_id,
                time,
                content,
                comment_format,
                playmode,
                color
            )
        )
        instance.commit()
    
    def submit_screenshot(
        self,
        user_id: int,
        hidden: bool
    ) -> int:
        instance = self.session
        instance.add(
            ss := DBScreenshot(
                user_id,
                hidden
            )
        )
        instance.commit()

        return ss.id

    def submit_activity(self, user_id: int, mode: int, text: str, args: str, links: str):
        instance = self.session
        instance.add(
            DBActivity(
                user_id,
                mode,
                text,
                args,
                links
            )
        )
        instance.commit()

    def create_plays(self, user_id: int, beatmap_id: int, beatmap_file: str, set_id: int) -> DBPlay:
        instance = self.session
        instance.add(
            plays := DBPlay(
                user_id,
                beatmap_id,
                set_id,
                beatmap_file
            )
        )
        instance.commit()

        return plays

    def update_plays(self, beatmap_id: int, beatmap_file: str, set_id: int, user_id: int):
        instance = self.session
        updated = instance.query(DBPlay) \
                .filter(DBPlay.beatmap_id == beatmap_id) \
                .filter(DBPlay.user_id == user_id) \
                .update({
                    'count': DBPlay.count + 1
                })

        if not updated:
            self.create_plays(
                user_id,
                beatmap_id,
                beatmap_file,
                set_id
            )

        instance.commit()

    def update_replay_views(self, user_id: int, mode: int):
        instance = app.session.database.session
        instance.query(DBStats) \
                .filter(DBStats.user_id == user_id) \
                .filter(DBStats.mode == mode) \
                .update({
                    'replay_views': DBStats.replay_views + 1
                })
        instance.commit()

    def update_latest_activity(self, user_id: int):
        Thread(
            target=self.__update_latest_activity,
            args=[user_id],
            daemon=True
        ).start()

    def __update_latest_activity(self, user_id: int):
        instance = self.session
        instance.query(DBUser) \
                .filter(DBUser.id == user_id) \
                .update({
                    'latest_activity': datetime.now()
                })
        instance.commit()

    def update_rank_history(self, stats: DBStats):
        country_rank = app.session.cache.get_country_rank(stats.user_id, stats.mode, stats.user.country)
        global_rank = app.session.cache.get_global_rank(stats.user_id, stats.mode)
        score_rank = app.session.cache.get_score_rank(stats.user_id, stats.mode)

        if global_rank <= 0:
            return

        instance = self.session
        instance.add(
            DBRankHistory(
                stats.user_id,
                stats.mode,
                stats.rscore,
                stats.pp,
                global_rank,
                country_rank,
                score_rank
            )
        )
        instance.commit()

    def update_plays_history(self, user_id: int, mode: int, time = datetime.now()):
        instance = self.session
        updated = instance.query(DBPlayHistory) \
                        .filter(DBPlayHistory.user_id == user_id) \
                        .filter(DBPlayHistory.mode == mode) \
                        .filter(DBPlayHistory.year == time.year) \
                        .filter(DBPlayHistory.month == time.month) \
                        .update({
                            'plays': DBPlayHistory.plays + 1
                        })

        if not updated:
            instance.add(
                DBPlayHistory(
                    user_id,
                    mode,
                    plays=1,
                    time=time
                )
            )

        instance.commit()

    def update_replay_history(self, user_id: int, mode: int, time = datetime.now()):
        instance = self.session
        updated = instance.query(DBReplayHistory) \
                        .filter(DBReplayHistory.user_id == user_id) \
                        .filter(DBReplayHistory.mode == mode) \
                        .filter(DBReplayHistory.year == time.year) \
                        .filter(DBReplayHistory.month == time.month) \
                        .update({
                            'replay_views': DBReplayHistory.replay_views + 1
                        })

        if not updated:
            instance.add(
                DBReplayHistory(
                    user_id,
                    mode,
                    replay_views=1,
                    time=time
                )
            )

        instance.commit()
