import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    Enum,
    ForeignKey,
    Text,
    DateTime,
    Table,
    func,
)
from sqlalchemy.orm import relationship
from app.database import Base


class UserRole(str, enum.Enum):
    """User roles for issue tracking and access control."""
    ADMIN = "Admin"
    DEVELOPER = "Developer"
    VIEWER = "Viewer"


class TicketType(str, enum.Enum):
    """Ticket category."""
    BUG = "Bug"
    TASK = "Task"
    FEATURE = "Feature"


class TicketStatus(str, enum.Enum):
    """Ticket workflow state."""
    TO_DO = "To Do"
    IN_PROGRESS = "In Progress"
    DONE = "Done"


class TicketPriority(str, enum.Enum):
    """Ticket urgency level."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


# Association table for Project <-> User many-to-many team membership
project_members = Table(
    "project_members",
    Base.metadata,
    Column(
        "project_id",
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "user_id",
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class User(Base):
    """SQLAlchemy model representing application users."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(
        Enum(UserRole, name="user_role", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=UserRole.DEVELOPER,
    )
    is_active = Column(Boolean, nullable=False, default=True)

    # Relationships
    owned_projects = relationship("Project", back_populates="owner")
    projects = relationship(
        "Project",
        secondary=project_members,
        back_populates="members",
    )
    created_tickets = relationship(
        "Ticket",
        foreign_keys="Ticket.created_by",
        back_populates="creator",
    )
    assigned_tickets = relationship(
        "Ticket",
        foreign_keys="Ticket.assignee_id",
        back_populates="assignee",
    )
    # Day 9: comments authored by this user
    comments = relationship(
        "Comment",
        foreign_keys="Comment.author_id",
        back_populates="author",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class Project(Base):
    """SQLAlchemy model representing issue tracking projects."""
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    owner_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Relationships
    owner = relationship("User", back_populates="owned_projects")
    members = relationship(
        "User",
        secondary=project_members,
        back_populates="projects",
    )
    tickets = relationship(
        "Ticket",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, name='{self.name}', owner_id={self.owner_id})>"


class Ticket(Base):
    """SQLAlchemy model representing issues/tickets in a project."""
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    type = Column(
        Enum(TicketType, name="ticket_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TicketType.BUG,
    )
    status = Column(
        Enum(TicketStatus, name="ticket_status", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TicketStatus.TO_DO,
    )
    priority = Column(
        Enum(TicketPriority, name="ticket_priority", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TicketPriority.MEDIUM,
    )
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assignee_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    project = relationship("Project", back_populates="tickets")
    creator = relationship(
        "User",
        foreign_keys=[created_by],
        back_populates="created_tickets",
    )
    assignee = relationship(
        "User",
        foreign_keys=[assignee_id],
        back_populates="assigned_tickets",
    )
    # Day 9: top-level comments on this ticket (excludes replies; replies are
    # accessed through Comment.replies).  cascade ensures comments are removed
    # when the ticket is deleted.
    comments = relationship(
        "Comment",
        back_populates="ticket",
        cascade="all, delete-orphan",
        primaryjoin="Comment.ticket_id == Ticket.id",
    )

    def __repr__(self) -> str:
        return f"<Ticket(id={self.id}, title='{self.title}', status='{self.status}')>"


# =============================================================================
# Day 9 – Comment model
# =============================================================================

class Comment(Base):
    """SQLAlchemy model representing a comment on a ticket.

    Supports one-level threading via the self-referential ``parent_id`` FK:
    - ``parent_id IS NULL``  → top-level comment.
    - ``parent_id = <id>``   → reply to that top-level comment.

    Cascade rules:
    - Deleting a ticket removes all its comments (CASCADE from tickets.id).
    - Deleting a parent comment removes its replies (CASCADE from comments.id).
    - Deleting the author is restricted while they have comments (RESTRICT).
    """

    __tablename__ = "comments"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Comment text – required, non-empty enforced at schema layer
    body = Column(Text, nullable=False)

    # Foreign key → tickets.id
    # ON DELETE CASCADE: removing the ticket removes all its comments.
    ticket_id = Column(
        Integer,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Foreign key → users.id (the comment author)
    # ON DELETE RESTRICT: cannot delete a user who still has comments.
    author_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Self-referential FK for threading (nullable = top-level comment)
    # ON DELETE CASCADE: removing a parent comment removes its replies.
    parent_id = Column(
        Integer,
        ForeignKey("comments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Timestamp
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # ------------------------------------------------------------------
    # Relationships
    # ------------------------------------------------------------------

    # Back-reference to the ticket this comment belongs to
    ticket = relationship(
        "Ticket",
        back_populates="comments",
        foreign_keys=[ticket_id],
    )

    # The user who wrote this comment
    author = relationship(
        "User",
        back_populates="comments",
        foreign_keys=[author_id],
    )

    # Self-referential: one-level replies
    # ``remote_side=[id]`` tells SQLAlchemy that "id" is on the "one" side
    # (the parent), making ``parent_id`` the FK on the "many" (replies) side.
    parent = relationship(
        "Comment",
        back_populates="replies",
        remote_side="Comment.id",
        foreign_keys=[parent_id],
    )
    replies = relationship(
        "Comment",
        back_populates="parent",
        foreign_keys="Comment.parent_id",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<Comment(id={self.id}, ticket_id={self.ticket_id}, "
            f"author_id={self.author_id}, parent_id={self.parent_id})>"
        )
