from pydantic import BaseModel, Field


class LoginToDysInput(BaseModel):
    user_id: int = Field(description="Telegram user id.")
    session_id: str = Field(description="Active runtime session id.")
    email: str = Field(description="Student email.")
    password: str = Field(description="Student password.")
    university_url: str = Field(description="University DYS entry URL.")


class JoinTeamsMeetingInput(BaseModel):
    user_id: int
    session_id: str
    course_id: int
    course_name: str


class LeaveMeetingInput(BaseModel):
    user_id: int
    session_id: str


class TakeScreenshotInput(BaseModel):
    user_id: int
    session_id: str


class RequestHumanInputInput(BaseModel):
    user_id: int
    session_id: str
    tool_name: str
    reason: str
    prompt: str
    screenshot_path: str | None = None
