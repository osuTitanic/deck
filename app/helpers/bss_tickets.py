

from dataclasses import dataclass, asdict, field
from osz2 import MetadataType
from typing import Dict, List
from app import utils

import base64
import json
import app

@dataclass
class UploadTicket:
    filename: str
    ticket: str
    file: bytes

@dataclass
class UploadRequest:
    set_id: int
    osz_ticket: str
    has_video: bool
    has_storyboard: bool
    metadata: Dict[str, str] = field(default_factory=dict)
    is_update: bool = False
    tickets: List[UploadTicket] = field(default_factory=list)

    @property
    def osz_filename(self) -> str:
        return utils.sanitize_filename(
            f'{self.set_id} '
            f'{self.metadata[MetadataType.Artist.name]} - {self.metadata[MetadataType.Title.name]} '
            f'({self.metadata[MetadataType.Creator.name]})'
        ) + '.osz'

def register_upload_request(user_id: int, request: UploadRequest) -> None:
    request_dict = asdict(request)

    for ticket in request_dict['tickets']:
        # Serialize the binary file data to base64
        ticket['file'] = base64.b64encode(ticket['file']).decode()

    serialized_request = json.dumps(request_dict)
    app.session.redis.set(f'beatmap_upload:{user_id}', serialized_request, ex=3600)

def get_upload_request(user_id: int) -> UploadRequest | None:
    if not (serialized_request := app.session.redis.get(f'beatmap_upload:{user_id}')):
        return

    request_dict = json.loads(serialized_request)

    for ticket in request_dict['tickets']:
        # Deserialize the base64 file data to binary
        ticket['file'] = base64.b64decode(ticket['file'])

    tickets = [
        UploadTicket(**ticket)
        for ticket in request_dict['tickets']
    ]

    request = UploadRequest(**request_dict)
    request.tickets = tickets
    return request

def upload_request_exists(user_id: int) -> bool:
    return app.session.redis.exists(f'beatmap_upload:{user_id}')

def remove_upload_request(user_id: int) -> None:
    app.session.redis.delete(f'beatmap_upload:{user_id}')
