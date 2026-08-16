
from starlette.datastructures import UploadFile as StarletteUploadFile
from fastapi import Request, Response, HTTPException
from typing import Callable, List, Any
from app.common import officer
from functools import wraps

def comma_list(parameter: str, cast=str) -> Callable:
    async def wrapper(request: Request) -> List[Any]:
        try:
            query = request.query_params.get(parameter, '')
            return [cast(value) for value in query.split(',')]
        except ValueError:
            raise HTTPException(400, 'Invalid query parameter')
    return wrapper

def integer_boolean_query(parameter: str) -> Callable:
    async def wrapper(request: Request) -> bool:
        query = request.query_params.get(parameter, '0')
        return query == '1'
    return wrapper

def integer_boolean_form(parameter: str) -> Callable:
    async def wrapper(request: Request) -> bool:
        form = await request.form()
        query = form.get(parameter, '0')
        return query == '1'
    return wrapper

def integer_boolean(parameter: str) -> Callable:
    async def wrapper(request: Request) -> bool:
        query = request.query_params.get(parameter)

        if query is not None:
            return query == '1'

        # Try to use form data as a backup
        form = await request.form()
        query = form.get(parameter)
        return query == '1'
    return wrapper

def query_or_form(alias: str) -> Callable:
    async def wrapper(request: Request) -> StarletteUploadFile | str:
        query = request.query_params.get(alias)

        if query is not None:
            return query

        form = await request.form()

        if alias not in form:
            raise HTTPException(
                status_code=400,
                detail=f'Missing required parameter: {alias}'
            )

        return form[alias]
    return wrapper

def file(*aliases) -> Callable:
    async def wrapper(request: Request) -> StarletteUploadFile | str:
        form = await request.form()

        for alias in aliases:
            if alias in form:
                return form[alias]

        raise HTTPException(
            status_code=400,
            detail=f'Missing required file parameter: {", ".join(aliases)}'
        )
    return wrapper

def catch_bss_errors(
    message: str = "A server error occurred. Please try again!",
    legacy: bool = False
) -> Callable:
    def decorator(func) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Response:
            try:
                return func(*args, **kwargs)
            except AssertionError as e:
                assertion_msg = str(e)
                response_msg = f"Your beatmapset could not be updated: {assertion_msg}"
                officer.call(f"Failed to process bss request: {assertion_msg}")

                if session := kwargs.get('session'):
                    session.rollback()

                return error_response(5, response_msg, legacy=legacy)
            except Exception as e:
                officer.call(
                    f'Failed to execute {func.__name__}.',
                    exc_info=e
                )

                if session := kwargs.get('session'):
                    session.rollback()

                return error_response(5, message, legacy=legacy)
        return wrapper
    return decorator

def error_response(
    error_code: int,
    message: str = "",
    legacy: bool = False
) -> Response:
    if not legacy:
        return Response(f'{error_code}\n{message}')

    message_dict = {
        1: "The beatmap you're trying to submit isn't owned by you.",
        2: "The beatmap you're trying to submit is no longer available.",
        3: "The beatmap is already ranked. You cannot update ranked maps.",
        4: "The beatmap is currently in the beatmap graveyard. You can ungraveyard your map by visiting the beatmaps section of your user profile.",
        5: "An error occurred while processing your beatmap."
    }

    fallback_message = message_dict.get(
        error_code,
        'An unknown error occurred.'
    )

    return Response(message or fallback_message)
