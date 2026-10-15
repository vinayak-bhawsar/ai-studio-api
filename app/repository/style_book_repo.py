import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.stylebook import StyleBook


def get_style_book_by_project(
    db: Session,
    project_id: uuid.UUID,
) -> StyleBook | None:
    statement = select(StyleBook).where(
        StyleBook.project_id == project_id,
    )

    return db.scalar(statement)


def create_style_book(
    db: Session,
    project_id: uuid.UUID,
    content: dict,
) -> StyleBook:
    style_book = StyleBook(
        project_id=project_id,
        content=content,
    )

    db.add(style_book)
    db.flush()

    return style_book


def update_style_book(
    db: Session,
    style_book: StyleBook,
    content: dict,
) -> StyleBook:
    style_book.content = content

    db.flush()

    return style_book