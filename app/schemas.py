from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import UserRole, TicketType, TicketStatus, TicketPriority


# =====================================================================
# Authentication Schemas (Day 2 - Preserved)
# =====================================================================

class UserCreate(BaseModel):
    """Schema for public user registration."""

    model_config = ConfigDict(extra="forbid")

    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        description="User display name / identifier for issue tracking",
    )
    email: EmailStr = Field(
        ...,
        description="Valid email address used for login",
    )
    password: str = Field(
        ...,
        min_length=6,
        description="Account password (minimum 6 characters, maximum 72 UTF-8 bytes)",
    )

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, v: str) -> str:
        """Validate bcrypt's 72-byte password limit."""
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password cannot exceed 72 UTF-8 bytes in length")
        return v


class UserLogin(BaseModel):
    """Schema for user login credentials."""

    email: EmailStr
    password: str = Field(..., min_length=1)

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, v: str) -> str:
        """Validate bcrypt's 72-byte password limit."""
        if len(v.encode("utf-8")) > 72:
            raise ValueError("Password cannot exceed 72 UTF-8 bytes in length")
        return v


class UserResponse(BaseModel):
    """Safe user response schema. Excludes password information."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    role: UserRole
    is_active: bool


class Token(BaseModel):
    """Schema for returning the JWT access token."""

    access_token: str
    token_type: str = "bearer"


# =====================================================================
# Project & Team Management Schemas (Day 3 - Preserved)
# =====================================================================

class ProjectCreate(BaseModel):
    """Schema for creating a new project."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Project name (1 to 100 characters)",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional project description (up to 500 characters)",
    )


class ProjectUpdate(BaseModel):
    """Schema for updating an existing project (supports partial updates)."""

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Updated project name (1 to 100 characters)",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Updated project description (up to 500 characters)",
    )


class ProjectResponse(BaseModel):
    """Schema for project responses with ORM serialization."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: Optional[str] = None
    owner_id: int
    created_at: datetime


class ProjectMemberAdd(BaseModel):
    """Schema for adding a team member to a project."""

    user_id: int = Field(
        ...,
        gt=0,
        description="User ID of the member to add (must be greater than 0)",
    )


class UserSummaryResponse(BaseModel):
    """Safe user summary response for project team members (excludes password fields)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: EmailStr
    role: UserRole
    is_active: bool


# =====================================================================
# Ticket Schemas (Day 4)
# =====================================================================

class TicketCreate(BaseModel):
    """Schema for creating a new ticket. created_by is assigned from the JWT user."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Ticket title (1 to 200 characters)",
    )
    description: Optional[str] = Field(
        default=None,
        description="Optional ticket description",
    )
    type: TicketType = Field(
        default=TicketType.BUG,
        description="Ticket category: Bug, Task, or Feature",
    )
    status: TicketStatus = Field(
        default=TicketStatus.TO_DO,
        description="Workflow state: To Do, In Progress, or Done",
    )
    priority: TicketPriority = Field(
        default=TicketPriority.MEDIUM,
        description="Urgency level: Low, Medium, or High",
    )
    project_id: int = Field(
        ...,
        gt=0,
        description="ID of the project this ticket belongs to",
    )
    assignee_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional user ID of an active project member to assign",
    )

    @field_validator("title")
    @classmethod
    def validate_title_not_whitespace(cls, v: str) -> str:
        """Reject whitespace-only titles and strip leading/trailing whitespace."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Ticket title cannot be empty or contain only whitespace")
        return stripped


class TicketUpdate(BaseModel):
    """Schema for updating an existing ticket (supports partial updates).

    - Omitted fields are ignored (partial update via exclude_unset).
    - `type`, `status`, and `priority` are non-nullable: explicit null is rejected.
    - `description` accepts null to clear the description.
    - `assignee_id` accepts null to unassign; positive integer to assign.
    """

    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Updated ticket title (1 to 200 characters)",
        
    )
    description: Optional[str] = Field(
        default=None,
        description="Updated ticket description (null clears it)",
    )
    type: Optional[TicketType] = Field(
        default=None,
        description="Updated ticket category: Bug, Task, or Feature (cannot be null)",
        
    )
    status: Optional[TicketStatus] = Field(
        default=None,
        description="Updated workflow state: To Do, In Progress, or Done (cannot be null)",
        
    )
    priority: Optional[TicketPriority] = Field(
        default=None,
        description="Updated priority level: Low, Medium, or High (cannot be null)",
        
    )
    assignee_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Updated assignee user ID (pass null to unassign)",
    )

    @field_validator("title")
    @classmethod
    def validate_title_not_whitespace(cls, v: Optional[str]) -> Optional[str]:
        """Reject whitespace-only titles and strip leading/trailing whitespace if provided."""
        if v is not None:
            stripped = v.strip()
            if not stripped:
                raise ValueError("Ticket title cannot be empty or contain only whitespace")
            return stripped
        return v

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_null_for_non_nullable_fields(cls, values: dict) -> dict:
        """Reject explicit null for type, status, and priority (non-nullable columns)."""
        non_nullable = ("type", "status", "priority")
        for field_name in non_nullable:
            if field_name in values and values[field_name] is None:
                raise ValueError(
                    f"'{field_name}' cannot be null; omit the field to leave it unchanged"
                )
        return values


class TicketResponse(BaseModel):
    """Schema for ticket responses with ORM serialization."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    type: TicketType
    status: TicketStatus
    priority: TicketPriority
    project_id: int
    assignee_id: Optional[int] = None
    created_by: int
    created_at: datetime
    updated_at: datetime


# =====================================================================
# Comment Schemas (Day 9)
# =====================================================================

class CommentAuthorResponse(BaseModel):
    """Minimal author info embedded inside a CommentResponse.

    Exposes only id and username — enough for the UI to display the
    author's name without leaking email or role data.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str


class CommentCreate(BaseModel):
    """Schema for posting a new comment on a ticket.

    - ``body``      — required; whitespace-only text is rejected.
    - ``parent_id`` — optional; when supplied the comment is a reply to
                      that parent comment.  Must be a positive integer.
                      The API layer will verify the parent belongs to the
                      same ticket (prevents cross-ticket reply injection).
    """

    model_config = ConfigDict(extra="forbid")

    body: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Comment text (1 to 5000 characters)",
    )
    parent_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="ID of the parent comment when posting a reply (omit for top-level)",
    )

    @field_validator("body")
    @classmethod
    def validate_body_not_whitespace(cls, v: str) -> str:
        """Reject whitespace-only comment bodies."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Comment body cannot be empty or contain only whitespace")
        return stripped


class CommentResponse(BaseModel):
    """Schema for a single comment, including its one-level replies.

    Fields
    ------
    id          : Primary key of this comment.
    body        : Comment text.
    ticket_id   : The ticket this comment belongs to.
    author_id   : User ID of the author (integer FK).
    author      : Minimal author object (id + username) for display.
    parent_id   : NULL for top-level comments; parent comment ID for replies.
    created_at  : UTC timestamp of when the comment was created.
    replies     : List of direct replies (one level deep).  Empty list for
                  reply comments themselves (the API will not nest further).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    body: str
    ticket_id: int
    author_id: int
    author: CommentAuthorResponse
    parent_id: Optional[int] = None
    created_at: datetime
    replies: list["CommentResponse"] = []


# Required by Pydantic v2 to resolve the self-referential annotation
# ("CommentResponse" inside its own replies list).
CommentResponse.model_rebuild()
