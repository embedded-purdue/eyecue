"""Shared runtime singleton for routes."""

from __future__ import annotations

from app.services.pipeline_controller import PipelineController


pipeline_controller = PipelineController()
