from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import PublishedPost


def get_destination_publication(
    db: Session, *, artifact_id: int, destination: str
) -> PublishedPost | None:
    return (
        db.query(PublishedPost)
        .filter(
            PublishedPost.artifact_id == artifact_id,
            PublishedPost.destination == destination,
        )
        .one_or_none()
    )


def destination_already_published(db: Session, *, artifact_id: int, destination: str) -> bool:
    existing = get_destination_publication(db, artifact_id=artifact_id, destination=destination)
    return existing is not None and existing.status == "published"
