"""Optional LangGraph-native graph callback: observation, never authorization."""
from __future__ import annotations
from typing import Callable, Any
try:
    from langgraph.callbacks import GraphCallbackHandler
except ImportError:
    class GraphCallbackHandler:  # runtime requires langgraph for actual callback delivery
        pass

class LoopGridGraphCallback(GraphCallbackHandler):
    """Observe real LangGraph checkpoint interrupt/resume events without claiming approval.

    Callbacks do NOT gate execution or write consequential signed events. A caller may
    emit sanitized telemetry through on_observation. Provide none for a no-op observer.
    """
    def __init__(self, on_observation: Callable[[dict[str,Any]],None] | None = None):
        super().__init__()
        self._on_observation = on_observation

    def _record(self, kind: str, event: Any):
        if self._on_observation is None: return
        self._on_observation({"framework":"langgraph", "kind":kind,
            "run_id":str(getattr(event,"run_id","") or ""),
            "checkpoint_id":str(getattr(event,"checkpoint_id","") or ""),
            "checkpoint_ns":list(getattr(event,"checkpoint_ns",()) or ())})

    def on_interrupt(self,event:Any)->None:
        self._record("checkpoint_interrupted",event)

    def on_resume(self,event:Any)->None:
        self._record("checkpoint_resumed",event)
