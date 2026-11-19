
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import decode_access_token


# Extract Bearer token from the Authorization header.
_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Authenticate the request using a JWT Bearer token.

    1. Check for a missing token.
    2. Validate and decode the JWT.
    3. Extract the user ID from the sub claim.
    4. Retrieve the user from PostgreSQL.
    5. Reject inactive users.
    """

    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Check whether the token is provided.
    if credentials is None:
        raise unauthorized

    token = credentials.credentials

    # Validate the JWT.
    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        raise unauthorized

    # Extract user ID.
    user_id = payload.get("sub")

    if user_id is None:
        raise unauthorized

    try:
        uid = int(user_id)
    except (ValueError, TypeError):
        raise unauthorized

    # Retrieve user from database.
    user = db.query(User).filter(User.id == uid).first()

    if user is None:
        raise unauthorized

    # Check account status.
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    return user
