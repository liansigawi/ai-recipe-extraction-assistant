"""Recipes' pictures and videos (app/media.py).

    GET    /api/media/{file_id}                     a saved picture or video (seeking in a video works)
    POST   /api/recipes/{id}/media                  upload a picture (the request body is the file)
    POST   /api/recipes/{id}/media/instagram        fetch the media of the recipe's Instagram post
    PUT    /api/recipes/{id}/cover                  choose the cover, or null for the first picture
    DELETE /api/recipes/{id}/media/{media_id}       remove an attachment (its file stays while another uses it)

None of these change the recipe's text, credit or categories; saving a recipe never changes its media.
"""

import logging
from pathlib import Path
from typing import Annotated

import httpx2
from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import crud, media, models
from app.api.imports import _READ_FAILURES, CaptionRetriever, get_caption_retriever
from app.db import get_session
from app.errors import ERROR_RESPONSES, ApiError, ErrorResponse
from app.importers.instagram import FetchOutcome, InvalidInstagramUrl, parse_instagram_url
from app.schemas import CoverChoice, MediaFetch, MediaFetchResult, Recipe

router = APIRouter(prefix="/api", tags=["media"])
log = logging.getLogger("uvicorn.error")
SessionDep = Annotated[Session, Depends(get_session)]
MEDIA_ERRORS = {
    **ERROR_RESPONSES,
    413: {"model": ErrorResponse, "description": "The file is larger than the limit"},
    415: {"model": ErrorResponse, "description": "Not a picture that can be saved"},
}

Transport = httpx2.BaseTransport | None
MediaRoot = Annotated[Path, Depends(media.get_media_root)]


@router.get("/media/{file_id}", responses=ERROR_RESPONSES)
def get_media_file(file_id: int, session: SessionDep, root: MediaRoot) -> FileResponse:
    """The file, with its type; it never changes (its name is its content), so the browser may keep it."""
    row = session.get(models.MediaFile, file_id)
    if row is None:
        raise ApiError(404, "media_not_found", f"There is no media file {file_id}.")
    path = media.file_path(root, row)
    if not path.exists():
        raise ApiError(404, "media_missing", "The file is no longer in the media folder.")
    return FileResponse(path, media_type=row.content_type, headers={"Cache-Control": "public, max-age=31536000, immutable"})


async def read_upload(request: Request) -> bytes:
    """The request body, up to the size limit (refused as soon as it is passed, not after)."""
    declared = int(request.headers.get("content-length") or 0)
    limit = media.MAX_UPLOAD_BYTES
    too_large = ApiError(413, "media_too_large", f"A picture can be up to {limit // 1_000_000} MB.")
    if declared > limit:
        raise too_large
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise too_large
    if not body:
        raise ApiError(422, "empty_upload", "The upload has no file in it.")
    return bytes(body)


@router.post("/recipes/{recipe_id}/media", status_code=status.HTTP_201_CREATED, responses=MEDIA_ERRORS)
def upload_media(recipe_id: int, data: Annotated[bytes, Depends(read_upload)], session: SessionDep, root: MediaRoot) -> Recipe:
    """A picture of yours, for any recipe (with or without an Instagram post): added after the others."""
    media.attach_upload(session, root, crud.load_recipe(session, recipe_id), data)
    session.expire_all()  # the recipe's media list changed
    return crud.get_recipe(session, recipe_id)


def instagram_url_of(recipe: models.Recipe) -> str | None:
    """The recipe's Instagram post: its imported original's address, else its first Instagram source."""
    addresses = [recipe.original.url] if recipe.original is not None and recipe.original.url else []
    addresses += [source.url for source in recipe.sources if source.url]
    for address in addresses:
        try:
            return parse_instagram_url(address).canonical_url
        except InvalidInstagramUrl:
            continue
    return None


@router.post("/recipes/{recipe_id}/media/instagram", responses=MEDIA_ERRORS)
def fetch_post_media(
    recipe_id: int,
    data: MediaFetch,
    session: SessionDep,
    root: MediaRoot,
    retrieve: Annotated[CaptionRetriever, Depends(get_caption_retriever)],
    transport: Annotated[Transport, Depends(media.get_media_transport)],
) -> MediaFetchResult:
    """Read the recipe's post again and save its pictures and videos here, in the post's order.

    Nothing else about the recipe changes: not its title, ingredients, steps, categories, credit or
    the picture on its card. Items it already has are not added again; a video saved only as its poster
    is tried again. No duplicate check: this is the recipe the post belongs to."""
    recipe = crud.load_recipe(session, recipe_id)
    shown = crud.get_recipe(session, recipe_id).cover_id  # the card's picture now
    url = data.url or instagram_url_of(recipe)
    if url is None:
        raise ApiError(422, "no_instagram_source", "The recipe has no Instagram post to take media from.")
    try:
        ref = parse_instagram_url(url)
    except InvalidInstagramUrl as error:
        raise ApiError(422, "invalid_instagram_url", str(error)) from None
    session.commit()  # nothing is read from the database during the page load
    retrieval = retrieve(ref)
    if not retrieval.media:
        if retrieval.outcome in (FetchOutcome.CAPTION_FOUND, FetchOutcome.CAPTION_INCOMPLETE, FetchOutcome.NO_CAPTION):
            raise ApiError(502, "instagram_no_media", "The post was read, but no pictures or videos were found in its data.")
        status_code, message = _READ_FAILURES.get(retrieval.outcome, _READ_FAILURES[FetchOutcome.ERROR])
        raise ApiError(status_code, f"instagram_{retrieval.outcome}", message, {"url": ref.canonical_url})
    report = media.attach_post_media(session, root, crud.load_recipe(session, recipe_id), ref, retrieval.media, transport)
    session.expire_all()
    if shown is not None and crud.get_recipe(session, recipe_id).cover_id != shown:
        # It was the cover by default (the first picture), and the post's items now come before it:
        # it stays on the card, now as the chosen cover.
        media.set_cover(session, crud.load_recipe(session, recipe_id), shown)
        session.expire_all()
    return MediaFetchResult(recipe=crud.get_recipe(session, recipe_id), report=report.schema())


@router.put("/recipes/{recipe_id}/cover", responses=ERROR_RESPONSES)
def choose_cover(recipe_id: int, data: CoverChoice, session: SessionDep) -> Recipe:
    """The picture (or a video's poster) shown on the recipe's card."""
    media.set_cover(session, crud.load_recipe(session, recipe_id), data.media_id)
    session.expire_all()
    return crud.get_recipe(session, recipe_id)


@router.delete("/recipes/{recipe_id}/media/{media_id}", responses=ERROR_RESPONSES)
def remove_media(recipe_id: int, media_id: int, session: SessionDep, root: MediaRoot) -> Recipe:
    """Remove one attachment from this recipe. Its file is deleted only if no other recipe uses it."""
    media.remove(session, root, crud.load_recipe(session, recipe_id), media_id)
    session.expire_all()
    return crud.get_recipe(session, recipe_id)

