from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User, UserRole
from app.schemas import UserCreate, UserLogin, UserResponse, Token
from app.security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
def register(user_in: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user account.

    - Validates that email and username are not already in use.
    - Hashes the password using bcrypt.
    - Assigns the Developer role automatically (cannot be chosen by the user).
    - Returns the created user without exposing any password data.
    """
    # 1. Check for duplicate email
    if db.query(User).filter(User.email == user_in.email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # 2. Check for duplicate username
    if db.query(User).filter(User.username == user_in.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )

    # 3. Hash the password
    hashed_pwd = hash_password(user_in.password)

    # 4. Create user — role is always Developer for public registration
    new_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hashed_pwd,
        role=UserRole.DEVELOPER,
        is_active=True,
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration failed due to a conflict",
        )

    return new_user


@router.post(
    "/login",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="Login and obtain a JWT access token",
)
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """
    Authenticate a user and return a JWT access token.

    - Looks up the user by email.
    - Verifies the password using bcrypt.
    - Rejects inactive accounts with HTTP 403.
    - Uses a generic error message for wrong credentials to prevent user enumeration.
    """
    # 1. Look up user by email
    user = db.query(User).filter(User.email == credentials.email).first()

    # 2. Verify credentials — generic message prevents email enumeration
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Reject inactive accounts
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    # 4. Generate JWT with user identity claims
    token_data = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role.value,
    }
    token = create_access_token(data=token_data)

    return Token(access_token=token, token_type="bearer")


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get the currently authenticated user",
)
def get_me(current_user: User = Depends(get_current_user)):
    """
    Return the profile of the currently authenticated user.

    - Requires a valid JWT Bearer token in the Authorization header.
    - Never exposes hashed_password or any credential data.
    """
    return current_user

