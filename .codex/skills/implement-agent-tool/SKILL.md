---
name: implement-agent-tool
description: Use when adding, modifying, or fixing a LangGraph tool in the DYS attendance agent. Triggers on: "add tool", "fix tool", "new tool", "implement [tool-name]", "tool returns wrong", "tool crashes". Covers the full lifecycle: Pydantic schema -> injected handler -> async implementation -> unit test -> registration in the tool builder.
allow_implicit_invocation: true
---

## Context

This project is a multi-tenant Telegram bot that automates university attendance through DYS and
Microsoft Teams. Tools are async handlers used by the LangGraph agent and executed through
application services provided by dependency injection.

The architecture standard is:

- tools do not import shared services as globals
- tools are built from an `AppContainer`
- Browser-use is used for semantic browser navigation
- Playwright is used for deterministic browser primitives

## Tool Contract

Every tool must:

1. accept a typed Pydantic v2 model as its single input
2. return `ToolResult`
3. wrap internal failures in `try/except`
4. enforce `MAX_TOOL_TIMEOUT` with `asyncio.wait_for`
5. log start and finish with `structlog`
6. attach a screenshot path when a meaningful browser action occurs

```python
from pydantic import BaseModel
from app.schemas import ToolResult

class MyToolInput(BaseModel):
    user_id: int
    course_id: int

class MyTool:
    def __init__(self, browser_pool, telegram_bot, llm_client, settings, logger):
        self.browser_pool = browser_pool
        self.telegram_bot = telegram_bot
        self.llm_client = llm_client
        self.settings = settings
        self.log = logger

    async def __call__(self, params: MyToolInput) -> ToolResult:
        ...
```

Callable classes are the preferred pattern because they are easier to test and extend. A closure
factory is acceptable when the tool is very small.

## Step-by-Step Implementation

### Step 1 - Define the input schema

Add the Pydantic model to `app/tools/schemas.py`. Use `Field(description=...)` so the agent can
reason about the parameters.

### Step 2 - Implement the handler

Create the tool in `app/tools/`. Inject dependencies through the constructor.

Patterns to follow:

**Get or create the browser context**

```python
context = await self.browser_pool.get_or_create_context(user_id=params.user_id)
```

**Use Browser-use for semantic navigation**

```python
from browser_use import Agent as BrowserAgent

agent = BrowserAgent(
    task="Open the student's DYS portal and navigate to the relevant course page.",
    llm=self.llm_client,
    browser_context=context,
)
result = await asyncio.wait_for(agent.run(), timeout=self.settings.max_tool_timeout)
```

**Use Playwright for deterministic primitives**

```python
page = await context.new_page()
await page.wait_for_load_state("networkidle")
await page.screenshot(path=path)
await page.close()
```

### Step 3 - Register the tool through the builder

Do not maintain a module-level global registry. Register tools through the dependency-aware builder.

```python
def build_tools(container: AppContainer) -> list[object]:
    return [
        LoginToDysTool(...),
        JoinTeamsMeetingTool(...),
        MyTool(...),
    ]
```

### Step 4 - Write tests

Create unit tests in `tests/unit/tools/`. Use fixtures from `tests/conftest.py`. Never create a
real browser in unit tests.

Test at least:

- success path
- timeout path
- no active session or no context path when relevant
- human-input pause path when relevant

### Step 5 - Update docs when behavior changes

If the tool introduces a new runtime rule, env var, or workflow expectation, update:

- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `CHANGELOG.md`
- `.env.example` if config changed

## Human Input Rules

If the tool needs user intervention:

- create a durable `human_input_requests` record
- include correlation to `session_id`, `user_id`, and tool name
- return a graceful `ToolResult`
- never leave the flow paused without a request ID

Typical cases:

- 2FA
- ambiguous course selection
- unrecoverable page state that needs user confirmation

## Edge Cases

| Scenario | Required behavior |
|---|---|
| BrowserContext not found or inactive | Return a graceful `ToolResult` with next-step guidance |
| Browser-use timeout | Log and return a non-throwing failure result |
| Blank screenshot | Wait for `networkidle`, retry once |
| Auth failure | Stop early, do not silently retry |
| Waiting room | Update meeting state and inform the user clearly |

## What Not To Do

- do not import `browser_pool`, `telegram_bot`, `settings`, or `llm_client` as globals
- do not use Playwright selectors as the main navigation strategy
- do not swallow human-input correlation details
- do not retry wrong-password flows automatically
- do not merge tool changes without tests
