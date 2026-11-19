from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Ticket, Project, User, UserRole, TicketStatus, TicketPriority, TicketType
from app.schemas import (
    TicketCreate,
    TicketUpdate,
    TicketResponse,
)

router = APIRouter(prefix="/tickets", tags=["Tickets"])


def _is_project_accessible(project: Project, user: User) -> bool:
    """Check if the user is authorized to view a project and its tickets."""
    if user.role == UserRole.ADMIN:
        return True
    if project.owner_id == user.id:
        return True
    return any(m.id == user.id for m in project.members)


def _is_valid_assignee(project: Project, user_id: int) -> bool:
    """
    Check if a user is the project owner or a member of the project eligible for assignment.
    Note: Active-user validation is performed separately by the create and update endpoints.
    """
    if project.owner_id == user_id:
        return True
    return any(m.id == user_id for m in project.members)


def _can_create_ticket(project: Project, user: User) -> bool:
    """Viewers cannot create tickets. Admins and project team members can."""
    if user.role == UserRole.VIEWER:
        return False
    return _is_project_accessible(project, user)


def _can_update_ticket(ticket: Ticket, user: User) -> bool:
    """
    Ticket update permissions (approved matrix):
    - Admin: can update all tickets across all projects.
    - Project Owner: can update any ticket in their own projects.
    - Developer / Project Member: can update tickets in projects they belong to.
    - Viewer: cannot update tickets (forbidden regardless of membership).
    - Non-member: cannot update tickets (forbidden).
    """
    if user.role == UserRole.VIEWER:
        return False
    return _is_project_accessible(ticket.project, user)


def _can_delete_ticket(ticket: Ticket, user: User) -> bool:
    """
    Ticket delete permissions (destructive):
    - Viewers: forbidden.
    - Admin: allowed.
    - Project Owner: allowed (in their projects).
    - Developer / Project Member: allowed for own created tickets only.
    - Other team members: forbidden.
    - Non-members: forbidden.
    """
    if user.role == UserRole.VIEWER:
        return False
    if user.role == UserRole.ADMIN:
        return True
    if ticket.project.owner_id == user.id:
        return True
    if ticket.created_by == user.id and _is_project_accessible(ticket.project, user):
        return True
    return False


# -----------------------------------------------------------------------------
# 1. POST /tickets — Create a ticket
# -----------------------------------------------------------------------------
@router.post(
    "",
    response_model=TicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new ticket",
)
def create_ticket(
    ticket_in: TicketCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new ticket within a project.
    - Viewers cannot create tickets.
    - Validates project exists and user has access to it.
    - Validates assignee (if provided) exists, is active, and belongs to the project.
    - Automatically records current_user.id as created_by (cannot be overridden).
    """
    # 1. Check viewer restriction
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot create tickets",
        )

    # 2. Validate project existence
    project = db.query(Project).filter(Project.id == ticket_in.project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    # 3. Validate user has access to this project
    if not _is_project_accessible(project, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this project",
        )

    # 4. Validate assignee if provided
    if ticket_in.assignee_id is not None:
        assignee_user = db.query(User).filter(User.id == ticket_in.assignee_id).first()
        if not assignee_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignee user not found",
            )
        if not assignee_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot assign ticket to inactive user",
            )
        if not _is_valid_assignee(project, assignee_user.id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Assignee must be a member of the project",
            )

    # 5. Create ticket with server-enforced creator
    new_ticket = Ticket(
        title=ticket_in.title,
        description=ticket_in.description,
        type=ticket_in.type,
        status=ticket_in.status,
        priority=ticket_in.priority,
        project_id=ticket_in.project_id,
        assignee_id=ticket_in.assignee_id,
        created_by=current_user.id,
    )

    try:
        db.add(new_ticket)
        db.commit()
        db.refresh(new_ticket)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ticket",
        )

    return new_ticket


# -----------------------------------------------------------------------------
# 2. GET /tickets — List accessible tickets
# -----------------------------------------------------------------------------
@router.get(
    "",
    response_model=list[TicketResponse],
    status_code=status.HTTP_200_OK,
    summary="List tickets accessible to the logged-in user",
)
def list_tickets(
    project_id: Optional[int] = None,
    status_filter: Optional[TicketStatus] = None,
    priority_filter: Optional[TicketPriority] = None,
    type_filter: Optional[TicketType] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List tickets accessible to the logged-in user.
    - Admins see all tickets (or filtered by project).
    - Developers and Viewers only see tickets from projects they have access to.
    - Optional filters: project_id, status_filter, priority_filter, type_filter, search.
    """
    query = db.query(Ticket).join(Project, Ticket.project_id == Project.id)

    # Apply project access scoping for non-admins
    if current_user.role != UserRole.ADMIN:
        query = query.filter(
            (Project.owner_id == current_user.id)
            | (Project.members.any(User.id == current_user.id))
        )

    # Optional project filter
    if project_id is not None:
        target_proj = db.query(Project).filter(Project.id == project_id).first()
        if not target_proj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found",
            )
        if not _is_project_accessible(target_proj, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this project",
            )
        query = query.filter(Ticket.project_id == project_id)

    # Optional attribute filters
    if status_filter is not None:
        query = query.filter(Ticket.status == status_filter)
    if priority_filter is not None:
        query = query.filter(Ticket.priority == priority_filter)
    if type_filter is not None:
        query = query.filter(Ticket.type == type_filter)

    # Optional keyword search filter across title OR description
    if search is not None:
        stripped_search = search.strip()
        if stripped_search:
            search_pattern = f"%{stripped_search}%"
            query = query.filter(
                or_(
                    Ticket.title.ilike(search_pattern),
                    Ticket.description.ilike(search_pattern),
                )
            )

    return query.distinct().all()


# -----------------------------------------------------------------------------
# 3. GET /tickets/{ticket_id} — Get ticket details
# -----------------------------------------------------------------------------
@router.get(
    "/{ticket_id}",
    response_model=TicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Get ticket details",
)
def get_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get details of a specific ticket.
    - User must have access to the ticket's parent project.
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
            detail="Access denied to this ticket",
        )

    return ticket


# -----------------------------------------------------------------------------
# 4. PUT /tickets/{ticket_id} — Update ticket details
# -----------------------------------------------------------------------------
@router.put(
    "/{ticket_id}",
    response_model=TicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a ticket",
)
def update_ticket(
    ticket_id: int,
    ticket_in: TicketUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update ticket details (partial updates supported).
    - Viewers and non-members cannot update tickets.
    - Admins, project owners, and project members can update.
    - Validates new assignee if provided.
    - created_by and project_id cannot be changed.
    """
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    if not _can_update_ticket(ticket, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied to update this ticket",
        )

    update_data = ticket_in.model_dump(exclude_unset=True)

    if "title" in update_data:
        title_val = update_data["title"]
        if title_val is None or len(title_val.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Ticket title cannot be empty",
            )
        ticket.title = title_val

    if "description" in update_data:
        ticket.description = update_data["description"]

    if "type" in update_data:
        ticket.type = update_data["type"]

    if "status" in update_data:
        ticket.status = update_data["status"]

    if "priority" in update_data:
        ticket.priority = update_data["priority"]

    if "assignee_id" in update_data:
        new_assignee_id = update_data["assignee_id"]
        if new_assignee_id is not None:
            assignee_user = db.query(User).filter(User.id == new_assignee_id).first()
            if not assignee_user:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Assignee user not found",
                )
            if not assignee_user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot assign ticket to inactive user",
                )
            if not _is_valid_assignee(ticket.project, assignee_user.id):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Assignee must be a member of the project",
                )
        ticket.assignee_id = new_assignee_id

    try:
        db.commit()
        db.refresh(ticket)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ticket",
        )

    return ticket


# -----------------------------------------------------------------------------
# 5. DELETE /tickets/{ticket_id} — Delete a ticket
# -----------------------------------------------------------------------------
@router.delete(
    "/{ticket_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a ticket",
)
def delete_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete a ticket.
    - Admins can delete all tickets.
    - Project owners can delete tickets in their projects.
    - Developers/project members can delete only tickets they created and only while they have project access.
    - Viewers and non-members cannot delete tickets.
    """
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ticket not found",
        )

    if not _can_delete_ticket(ticket, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins, project owners, or ticket creators with project access can delete this ticket",
        )

    try:
        db.delete(ticket)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete ticket",
        )

    return None
