"""Audit trail package for ai-gen."""

from .trail import get_events, get_summary, record_event

__all__ = ["record_event", "get_events", "get_summary"]
