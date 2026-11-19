from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Comment, Ticket, User, UserRole
from app.schemas import CommentCreate, CommentResponse
from app.tickets import _is_project_accessible

router = APIRouter(prefix="/tickets", tags=["Comments"])


# -----------------------------------------------------------------------------
# 1. GET /tickets/{ticket_id}/comments — List comments for a ticket
# -----------------------------------------------------------------------------
@router.get(
    "/{ticket_id}/comments",
    response_model=list[CommentResponse],
    status_code=status.HTTP_200_OK,
    summary="List comments for a ticket",
)
def list_comments(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List threaded comments for a specific ticket.
    - Validates ticket exists (404 if not found).
    - Validates user has project access (403 if non-member).
    - Admins, Developers, and Viewers with project access can view comments.
    - Returns top-level comments and their one-level replies in chronological order.
    """
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    if not _is_project_accessible(ticket.project, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this ticket's comments",
        )

    # Fetch top-level comments (parent_id IS NULL) in chronological order
    # Eagerly load author and direct replies
    top_level_comments = (
        db.query(Comment)
        .options(
            selectinload(Comment.author),
            selectinload(Comment.replies).selectinload(Comment.author),
        )
        .filter(Comment.ticket_id == ticket_id, Comment.parent_id.is_(None))
        .order_by(Comment.created_at.asc(), Comment.id.asc())
        .all()
    )

    # Ensure replies within each top-level comment are sorted chronologically
    for c in top_level_comments:
        c.replies.sort(key=lambda r: (r.created_at, r.id))

    return top_level_comments


# -----------------------------------------------------------------------------
# 2. POST /tickets/{ticket_id}/comments — Create a comment or reply
# -----------------------------------------------------------------------------
@router.post(
    "/{ticket_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Post a comment or reply on a ticket",
)
def create_comment(
    ticket_id: int,
    comment_in: CommentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a top-level comment or a one-level reply on a ticket.
    - Validates ticket exists (404 if not found).
    - Validates user has project access (403 if non-member).
    - Viewers cannot post or reply (403 forbidden).
    - Threading validation:
      - parent_id is null: creates a top-level comment.
      - parent_id provided: validates parent exists (404), belongs to the same ticket (400),
        and is a top-level comment (400 if replying to a reply).
    - author_id is always taken from current_user (server-enforced).
    """
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    # Permission check 1: project accessibility
    if not _is_project_accessible(ticket.project, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this ticket's comments",
        )

    # Permission check 2: Viewers cannot post comments or replies
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot post or reply to comments",
        )

    # Threading validation for replies
    if comment_in.parent_id is not None:
        parent_comment = db.query(Comment).filter(Comment.id == comment_in.parent_id).first()
        if not parent_comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent comment not found",
            )
        if parent_comment.ticket_id != ticket_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parent comment does not belong to this ticket",
            )
        if parent_comment.parent_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot reply to a reply; only one level of threading is supported",
            )

    new_comment = Comment(
        body=comment_in.body,
        ticket_id=ticket.id,
        author_id=current_user.id,
        parent_id=comment_in.parent_id,
    )

    try:
        db.add(new_comment)
        db.commit()
        db.refresh(new_comment)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create comment",
        )

    return new_comment

