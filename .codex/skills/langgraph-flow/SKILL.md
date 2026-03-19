---
name: langgraph-flow
description: Use when modifying the LangGraph agent graph: adding nodes, edges, state fields, or changing routing logic. Triggers on: "add agent state", "new graph node", "routing logic", "agent flow", "session memory", "thread", "langgraph". Also use when the agent misroutes user intent or mishandles paused human-input flows.
allow_implicit_invocation: true
---

## Context

The agent is a LangGraph StateGraph with one active thread per `session_id`. The session owns the
runtime conversation and control flow, while durable user and course data remain in PostgreSQL.

The full confirmed schedule is injected into the system prompt at session start and used for
semantic course matching.

## State Schema

Use a typed state object. At minimum, the state should include:

```python
from langgraph.graph import MessagesState
from typing import Optional

class AgentState(MessagesState):
    session_id: str
    user_id: int
    user_timezone: str
    schedule: list[dict]
    awaiting_human_input: bool
    pending_tool: Optional[str]
    pending_human_input_request_id: Optional[str]
    meeting_state: str
    last_screenshot_path: Optional[str]
```

If you add a field, update the initial state factory and the relevant tests.

## Graph Structure

```text
[START]
   |
   v
router_node
   |
   +-> CHAT -------> chat_response_node ----------> [END]
   |
   +-> CLARIFY ----> clarify_node ----------------> [END]
   |
   +-> TOOL_CALL --> tool_dispatch_node
                        |
                        v
                   tool_result_node --------------> [END]
```

Add a `human_input_resume_node` whenever paused flows need a dedicated resume path.

## Routing Rules

The router should:

1. check for an unresolved human-input pause first
2. if paused, route the next user reply to the resume path
3. otherwise classify into `CHAT`, `TOOL_CALL`, or `CLARIFY`

Do not replace semantic routing with regex or manual command parsing.

## Human Input Flow

`request_human_input` is a workflow contract, not just a message.

Required behavior:

1. the tool creates a durable `human_input_requests` row
2. the state stores `awaiting_human_input = true`
3. the state stores `pending_tool`
4. the state stores `pending_human_input_request_id`
5. the next user reply is correlated back to that request
6. the resume node continues the flow or closes it as expired

The state should never say it is paused without a corresponding request ID.

## Meeting State Coordination

Graph changes that affect attendance flow must respect explicit meeting states:

- `IDLE`
- `PREPARING`
- `LOGGING_IN`
- `JOINING`
- `WAITING_ROOM`
- `IN_MEETING`
- `LEAVING`
- `PAUSED_HUMAN_INPUT`
- `ERROR`

If you change meeting behavior, update both graph tests and architecture docs.

## Changing Routing Logic

When routing is wrong:

- inspect the prompt instructions first
- add or refine few-shot examples
- add a regression test
- only introduce structural graph changes if prompt correction is insufficient

## Testing Expectations

For graph changes, add tests that cover:

- normal tool routing
- clarify routing
- chat routing
- paused human-input resume behavior
- state initialization for new fields

Each node should remain independently testable as a state-in, state-out unit where practical.

## What Not To Do

- do not add ad hoc command parsing chains
- do not store durable schedule ownership inside session state
- do not treat restart as browser-context restore
- do not forget to propagate new state fields to initial graph state and fixtures
