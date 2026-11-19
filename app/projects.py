from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Project, User, UserRole
from app.schemas import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectMemberAdd,
    UserSummaryResponse,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


def _is_member(project: Project, user_id: int) -> bool:
    """Check if a user is in the project's member list."""
    return any(m.id == user_id for m in project.members)


def _can_access(project: Project, user: User) -> bool:
    """Project owner, team members, and Admins can view project details."""
    if user.role == UserRole.ADMIN:
        return True
    if project.owner_id == user.id:
        return True
    return _is_member(project, user.id)


def _can_manage(project: Project, user: User) -> bool:
    """Only project owner and Admins can update/delete project or manage members."""
    if user.role == UserRole.ADMIN:
        return True
    return project.owner_id == user.id


# -----------------------------------------------------------------------------
# 1. POST /projects — Create a project
# -----------------------------------------------------------------------------
@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
)
def create_project(
    project_in: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a new project.
    - Admin and Developer roles can create projects.
    - Viewer role is forbidden.
    - The creator is automatically set as owner and added as the first member.
    """
    if current_user.role == UserRole.VIEWER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot create projects",
        )

    new_project = Project(
        name=project_in.name,
        description=project_in.description,
        owner_id=current_user.id,
    )
    # Creator automatically becomes the first member
    new_project.members.append(current_user)

    try:
        db.add(new_project)
        db.commit()
        db.refresh(new_project)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create project",
        )

    return new_project


# -----------------------------------------------------------------------------
# 2. GET /projects — List accessible projects
# -----------------------------------------------------------------------------
@router.get(
    "",
    response_model=list[ProjectResponse],
    status_code=status.HTTP_200_OK,
    summary="List accessible projects",
)
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List projects accessible to the logged-in user.
    - Admins see all projects.
    - Developers and Viewers see projects they own or are members of.
    """
    if current_user.role == UserRole.ADMIN:
        return db.query(Project).all()

    return (
        db.query(Project)
        .filter(
            (Project.owner_id == current_user.id)
            | (Project.members.any(User.id == current_user.id))
        )
        .distinct()
        .all()
    )


# -----------------------------------------------------------------------------
# 3. GET /projects/{project_id} — Get project details
# -----------------------------------------------------------------------------
@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Get project details",
)
def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get details of a specific project.
    - Accessible to project owner, project team members, and Admins.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if not _can_access(project, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this project",
        )

    return project


# -----------------------------------------------------------------------------
# 4. PUT /projects/{project_id} — Update a project
# -----------------------------------------------------------------------------
@router.put(
    "/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Update project details",
)
def update_project(
    project_id: int,
    project_in: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update project name and/or description.
    - Only project owner and Admins can update.
    - Rejects explicitly supplied null project name.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if not _can_manage(project, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner or an admin can update this project",
        )

    update_data = project_in.model_dump(exclude_unset=True)

    if "name" in update_data:
        if update_data["name"] is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Project name cannot be null",
            )
        project.name = update_data["name"]

    if "description" in update_data:
        project.description = update_data["description"]

    try:
        db.commit()
        db.refresh(project)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update project",
        )

    return project


# -----------------------------------------------------------------------------
# 5. DELETE /projects/{project_id} — Delete a project
# -----------------------------------------------------------------------------
@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a project",
)
def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete a project and its member associations.
    - Only project owner and Admins can delete.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if not _can_manage(project, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner or an admin can delete this project",
        )

    try:
        db.delete(project)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete project",
        )

    return None


# -----------------------------------------------------------------------------
# 6. GET /projects/{project_id}/members — List team members
# -----------------------------------------------------------------------------
@router.get(
    "/{project_id}/members",
    response_model=list[UserSummaryResponse],
    status_code=status.HTTP_200_OK,
    summary="List project team members",
)
def list_project_members(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List members of a project.
    - Accessible to project owner, project team members, and Admins.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if not _can_access(project, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this project's member list",
        )

    return project.members


# -----------------------------------------------------------------------------
# 7. POST /projects/{project_id}/members — Add a team member
# -----------------------------------------------------------------------------
@router.post(
    "/{project_id}/members",
    response_model=UserSummaryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a team member to a project",
)
def add_project_member(
    project_id: int,
    member_in: ProjectMemberAdd,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Add a user to the project team.
    - Only project owner and Admins can add members.
    - Validates target user exists and is active.
    - Prevents adding duplicate members.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if not _can_manage(project, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner or an admin can add team members",
        )

    target_user = db.query(User).filter(User.id == member_in.user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not target_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot add inactive user to project",
        )

    if _is_member(project, target_user.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already a member of this project",
        )

    try:
        project.members.append(target_user)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add team member",
        )

    return target_user


# -----------------------------------------------------------------------------
# 8. DELETE /projects/{project_id}/members/{user_id} — Remove a team member
# -----------------------------------------------------------------------------
@router.delete(
    "/{project_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a team member from a project",
)
def remove_project_member(
    project_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Remove a user from the project team.
    - Only project owner and Admins can remove members.
    - The project owner cannot be removed from their own project.
    - Validates that the user is currently a project member.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if not _can_manage(project, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner or an admin can remove team members",
        )

    if user_id == project.owner_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove the project owner from their own project",
        )

    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if not _is_member(project, user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not a member of this project",
        )

    try:
        project.members.remove(target_user)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove team member",
        )

    return None
