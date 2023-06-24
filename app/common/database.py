
from sqlalchemy.orm import sessionmaker, scoped_session, Session
from sqlalchemy     import create_engine

from typing import Optional, Generator, List
from threading import Timer

from .objects import (
    DBBeatmapset,
    DBFavourite,
    DBComment,
    DBBeatmap,
    DBRating,
    DBUser,
    DBLog,
    Base
)

import traceback
import logging

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
            Timer(10, session.close).start()

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
