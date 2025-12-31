
from app.common.config import config_instance as config
from app.common.database.repositories import releases
from fastapi import APIRouter, Query

import app

router = APIRouter()

@router.get('/update')
def osume_update_endpoint(
    time: int = Query(0, alias='t'),
    current: int = Query(20140818, alias='v')
) -> str:
    with app.session.database.managed_session() as session:
        # NOTE: The "current" parameter is a custom parameter added by
        #       titanic that allows us to specify a custom version to use
        entry = releases.fetch_official_by_version(
            current,
            session=session
        )

        if not entry:
            return ""

        files = releases.fetch_file_entries(
            entry.id,
            session=session
        )

        if not files:
            return ""

        response = []

        for file in files:
            # For now, we only use "noup" action, because we currently
            # only have the "current" parameter to check for updates
            # For "diff" actions, we would need a second "from" parameter
            # that indicates where the user is updating from
            response.append(f"{file.filename} {file.file_hash} - noup {file.filename}")

        extras = releases.fetch_extras(session)

        for extra in extras:
            # It should be noted that "download" is the file to compare against
            # e.g. for "tutorial.zip" it would be "Songs/tutorial/bg.jpg" ->
            # If the file is present, the client will know that the tutorial is downloaded
            response.append(f"{extra.filename} {extra.md5} {extra.encoded_description} extra {extra.download}")

        return '\n'.join(response)

@router.get('/patches.php')
def patches() -> str:
    # TODO: Derive from "releases_files" -> "url_patch"
    return ""

@router.get('/update.php')
def ingame_update_check(
    filename: str = Query(..., alias='f'),
    checksum: str = Query(..., alias='h'),
    ticks: int = Query(..., alias='t')
) -> str:
    # TODO: Apply checks from bancho here
    return "0"

@router.get('/update2.php')
def ingame_update_check_but_better_i_guess() -> str:
    # TODO
    return ""
