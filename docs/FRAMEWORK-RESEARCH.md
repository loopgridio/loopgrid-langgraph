# LangGraph native research — Oct 12, 2026

Research target: [LangGraph 1.2.14](https://pypi.org/project/langgraph/1.2.14/), published Oct 6, 2026, Python >=3.10, supports stateful graph orchestration and checkpointed interruption.

Official API references:

- `StateGraph`, nodes and `START`/`END`: https://reference.langchain.com/python/langgraph/
- `interrupt(...)`, required checkpointer, `Command(resume=...)`: https://reference.langchain.com/python/langgraph/types/interrupt
- `GraphCallbackHandler`, `on_interrupt(event)`, `on_resume(event)`: https://reference.langchain.com/python/langgraph/callbacks/GraphCallbackHandler
- LangGraph interrupt/resume guide: https://docs.langchain.com/oss/python/langgraph/interrupts

**Key finding:** An interrupted node restarts **from its beginning** when resumed. Any action preceding an interrupt or replayed tool node can happen more than once absent separate safeguards. The LoopGrid native guarded tool node performs its own signed-receipt inspection, and must live downstream from the proposal node.

**Separate control boundaries:** A graph callback is an observation hook, not an execution guard. The actual guarded `StateGraph` node calls the authorized host callback only after Core policy, signed review and current action binding pass. `Command(resume=...)` is never signed human approval.

**Availability:** Real LangGraph 1.2.14 cannot be installed in the current development runtime due blocked PyPI network; an internet-enabled Windows and hosted GitHub CI check are explicit release gates.
