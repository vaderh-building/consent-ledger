"""Artist HTTP routes (includes the consent-policy lookup per spec)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_session
from app.domain.schemas import ArtistCreate, ArtistOut, ConsentPolicyOut
from app.services import artists as artists_svc
from app.services import consent_policies as policy_svc

router = APIRouter(prefix="/artists", tags=["artists"])


@router.post("", response_model=ArtistOut, status_code=status.HTTP_201_CREATED)
def create(payload: ArtistCreate, session: Session = Depends(get_session)) -> ArtistOut:
    try:
        artist = artists_svc.create_artist(
            session, rights_holder_id=payload.rights_holder_id, name=payload.name
        )
    except artists_svc.ArtistError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ArtistOut.model_validate(artist)


@router.get("", response_model=list[ArtistOut])
def list_all(session: Session = Depends(get_session)) -> list[ArtistOut]:
    return [ArtistOut.model_validate(a) for a in artists_svc.list_artists(session)]


@router.get("/{artist_id}", response_model=ArtistOut)
def get_one(artist_id: int, session: Session = Depends(get_session)) -> ArtistOut:
    a = artists_svc.get_artist(session, artist_id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="artist not found")
    return ArtistOut.model_validate(a)


@router.get("/{artist_id}/consent-policy", response_model=ConsentPolicyOut)
def get_consent_policy(
    artist_id: int,
    version: int | None = None,
    session: Session = Depends(get_session),
) -> ConsentPolicyOut:
    policy = (
        policy_svc.get_policy_version(session, artist_id, version)
        if version is not None
        else policy_svc.get_latest_policy(session, artist_id)
    )
    if policy is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"no consent policy found for artist {artist_id}"
                + (f" at version {version}" if version is not None else "")
            ),
        )
    return ConsentPolicyOut.model_validate(policy)
