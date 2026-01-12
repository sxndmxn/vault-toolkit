"""Common types and dataclasses for Vault Toolkit."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


@dataclass
class TimeRange:
    """A time range with start and end timestamps."""

    start: datetime
    end: datetime

    def __post_init__(self):
        if self.start > self.end:
            raise ValueError("start must be before end")

    @property
    def duration_seconds(self) -> float:
        """Duration of the time range in seconds."""
        return (self.end - self.start).total_seconds()

    def contains(self, dt: datetime) -> bool:
        """Check if a datetime falls within this range."""
        return self.start <= dt <= self.end

    def overlaps(self, other: "TimeRange") -> bool:
        """Check if this range overlaps with another."""
        return self.start <= other.end and other.start <= self.end


@dataclass
class Entity:
    """An extracted entity from data."""

    id: str
    entity_type: str
    value: str
    source_table: str
    source_row: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __hash__(self):
        return hash((self.entity_type, self.value))

    def __eq__(self, other):
        if not isinstance(other, Entity):
            return False
        return self.entity_type == other.entity_type and self.value == other.value


@dataclass
class Correlation:
    """A correlation between two entities or events."""

    source_entity: str
    target_entity: str
    correlation_type: str
    score: float
    timestamp: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Severity(Enum):
    """Anomaly severity levels."""

    LOW = "LOW"
    MEDIUM = "MED"
    HIGH = "HIGH"
    CRITICAL = "CRIT"


@dataclass
class AnomalyResult:
    """Result of anomaly detection."""

    timestamp: datetime
    entity_id: str | None
    severity: Severity
    anomaly_type: str
    description: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Gap:
    """A gap in timeline data."""

    start: datetime
    end: datetime
    source: str | None = None

    @property
    def duration_seconds(self) -> float:
        """Duration of the gap in seconds."""
        return (self.end - self.start).total_seconds()

    @property
    def duration_str(self) -> str:
        """Human-readable duration string."""
        seconds = self.duration_seconds
        if seconds < 60:
            return f"{seconds:.0f} seconds"
        elif seconds < 3600:
            return f"{seconds / 60:.0f} minutes"
        elif seconds < 86400:
            return f"{seconds / 3600:.1f} hours"
        else:
            return f"{seconds / 86400:.1f} days"


@dataclass
class GraphNode:
    """A node in a relationship graph."""

    id: str
    label: str
    node_type: str | None = None
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """An edge in a relationship graph."""

    source: str
    target: str
    edge_type: str | None = None
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)
