
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException, Response, Request
from app.server import api
from app import session

@api.exception_handler(HTTPException)
def exception_handler(request: Request, exc: HTTPException):
    headers = exc.headers if exc.headers else {}
    headers.update({'detail': exc.detail})

    return Response(
        status_code=exc.status_code,
        headers=headers
    )

@api.exception_handler(StarletteHTTPException)
def exception_handler(request: Request, exc: StarletteHTTPException):
    return Response(
        status_code=exc.status_code,
        headers={'detail': exc.detail}
    )

@api.exception_handler(RequestValidationError)
def validation_error(request: Request, exc: RequestValidationError):
    session.logger.error(f"Validation error: {exc.errors()}")
    return Response(
        status_code=400,
        content='no'
    )
