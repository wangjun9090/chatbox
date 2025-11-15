#!/usr/bin/env python3
"""
response_schema.py - Unified response format for all agents
Ensures consistent communication between master controller and agents
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any
from enum import Enum


class ResponseType(Enum):
    """Types of responses agents can return"""
    CHAT = "chat"           # General conversation
    HYMN = "hymn"           # Hymn search result
    SERMON = "sermon"       # Sermon search result
    ERROR = "error"         # Error occurred
    CLARIFICATION = "clarification"  # Need user clarification


class ActionType(Enum):
    """Actions the master should take with response"""
    SPEAK = "speak"         # Only speak the content
    PLAY = "play"           # Only play the audio
    BOTH = "both"           # Speak announcement then play
    NONE = "none"           # No action (error/clarification)


@dataclass
class AudioMetadata:
    """Metadata about an audio file"""
    title: str
    artist: Optional[str] = None
    source: Optional[str] = None  # "SmallChurchMusic", "Local File", etc.
    duration: Optional[int] = None  # seconds
    kind: Optional[str] = None  # "choir", "piano", "organ", etc.
    date: Optional[str] = None  # For sermons
    speaker: Optional[str] = None  # For sermons
    topic: Optional[str] = None  # For sermons
    
    def to_announcement(self) -> str:
        """Convert metadata to natural speech announcement"""
        if self.kind:
            return f"Playing {self.title} by {self.kind}"
        elif self.speaker:
            parts = [f"Playing {self.title}"]
            if self.speaker:
                parts.append(f"by {self.speaker}")
            if self.date:
                parts.append(f"from {self.date}")
            return " ".join(parts)
        else:
            return f"Playing {self.title}"


@dataclass
class AgentResponse:
    """
    Unified response format for all agents.
    Ensures consistent handling in master controller.
    """
    success: bool
    type: ResponseType
    content: str  # Text to speak or display
    
    # Audio playback fields
    url: Optional[str] = None  # Playable MP3 URL or file path
    metadata: Optional[AudioMetadata] = None
    
    # Quality/confidence metrics
    confidence: float = 1.0  # 0.0-1.0 confidence in response
    
    # Action directive
    action: ActionType = ActionType.SPEAK
    
    # Alternative options (for disambiguation)
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    
    # Error details (if applicable)
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    
    def __post_init__(self):
        """Validate response after initialization"""
        # Convert string types to enums if needed
        if isinstance(self.type, str):
            self.type = ResponseType(self.type)
        if isinstance(self.action, str):
            self.action = ActionType(self.action)
        
        # Validate confidence
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be 0.0-1.0, got {self.confidence}")
        
        # If action is PLAY or BOTH, must have URL
        if self.action in (ActionType.PLAY, ActionType.BOTH) and not self.url:
            raise ValueError(f"Action {self.action} requires a URL")
    
    def get_announcement(self) -> Optional[str]:
        """Get natural language announcement for audio playback"""
        if self.action in (ActionType.BOTH, ActionType.PLAY) and self.metadata:
            return self.metadata.to_announcement()
        return None
    
    def is_playable(self) -> bool:
        """Check if response contains playable audio"""
        return self.url is not None and self.success
    
    def needs_clarification(self) -> bool:
        """Check if response needs user clarification"""
        return self.type == ResponseType.CLARIFICATION or len(self.alternatives) > 1


# ============================================================================
# FACTORY FUNCTIONS - Convenient response builders
# ============================================================================

def chat_response(content: str, confidence: float = 1.0) -> AgentResponse:
    """Create a simple chat response"""
    return AgentResponse(
        success=True,
        type=ResponseType.CHAT,
        content=content,
        confidence=confidence,
        action=ActionType.SPEAK
    )


def hymn_response(
    url: str,
    title: str,
    kind: str = "choir",
    source: str = "Online",
    confidence: float = 1.0,
    alternatives: List[Dict] = None
) -> AgentResponse:
    """Create a hymn playback response"""
    metadata = AudioMetadata(
        title=title,
        kind=kind,
        source=source
    )
    
    return AgentResponse(
        success=True,
        type=ResponseType.HYMN,
        content=metadata.to_announcement(),
        url=url,
        metadata=metadata,
        confidence=confidence,
        action=ActionType.BOTH,
        alternatives=alternatives or []
    )


def sermon_response(
    url: str,
    title: str,
    speaker: Optional[str] = None,
    date: Optional[str] = None,
    topic: Optional[str] = None,
    confidence: float = 1.0
) -> AgentResponse:
    """Create a sermon playback response"""
    metadata = AudioMetadata(
        title=title,
        speaker=speaker,
        date=date,
        topic=topic,
        source="SermonAudio"
    )
    
    return AgentResponse(
        success=True,
        type=ResponseType.SERMON,
        content=metadata.to_announcement(),
        url=url,
        metadata=metadata,
        confidence=confidence,
        action=ActionType.BOTH
    )


def error_response(
    message: str,
    error_code: Optional[str] = None,
    details: Optional[str] = None
) -> AgentResponse:
    """Create an error response"""
    return AgentResponse(
        success=False,
        type=ResponseType.ERROR,
        content=message,
        confidence=0.0,
        action=ActionType.SPEAK,
        error_message=details,
        error_code=error_code
    )


def clarification_response(
    question: str,
    alternatives: List[Dict[str, Any]]
) -> AgentResponse:
    """Create a clarification request with options"""
    return AgentResponse(
        success=True,
        type=ResponseType.CLARIFICATION,
        content=question,
        confidence=0.5,
        action=ActionType.SPEAK,
        alternatives=alternatives
    )


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    # Example 1: Simple chat response
    resp1 = chat_response("The capital of France is Paris.")
    print(f"Chat: {resp1.content}")
    
    # Example 2: Hymn with playback
    resp2 = hymn_response(
        url="https://example.com/amazing-grace.mp3",
        title="Amazing Grace",
        kind="choir",
        confidence=0.95
    )
    print(f"Hymn: {resp2.get_announcement()}")
    print(f"  URL: {resp2.url}")
    print(f"  Playable: {resp2.is_playable()}")
    
    # Example 3: Sermon
    resp3 = sermon_response(
        url="https://sermonaudio.com/sermon.mp3",
        title="The Power of Forgiveness",
        speaker="Pastor John Smith",
        date="October 2024"
    )
    print(f"Sermon: {resp3.get_announcement()}")
    
    # Example 4: Error
    resp4 = error_response(
        message="I couldn't find that hymn.",
        error_code="HYMN_NOT_FOUND"
    )
    print(f"Error: {resp4.content}")
    
    # Example 5: Clarification
    resp5 = clarification_response(
        question="I found two versions. Did you want the choir or piano version?",
        alternatives=[
            {"title": "Amazing Grace - Choir", "url": "..."},
            {"title": "Amazing Grace - Piano", "url": "..."}
        ]
    )
    print(f"Clarification: {resp5.content}")
    print(f"  Needs clarification: {resp5.needs_clarification()}")
