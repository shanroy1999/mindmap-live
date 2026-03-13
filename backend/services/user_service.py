"""Business logic for user operations."""

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from models.user import User
from schemas.user import UserCreate

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_by_id(db: Session, user_id: str) -> User | None:
    """Return a user by ID, or None if not found."""
    return db.query(User).filter(User.id == user_id).first()


def get_by_email(db: Session, email: str) -> User | None:
    """Return a user by email address, or None if not found."""
    return db.query(User).filter(User.email == email).first()


def create(db: Session, payload: UserCreate) -> User:
    """Create and persist a new user with a bcrypt-hashed password."""
    user = User(
        email=payload.email,
        display_name=payload.display_name,
        hashed_password=_pwd_context.hash(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
