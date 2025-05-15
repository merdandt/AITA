# --- Pydantic Models ---
from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class DiscussionEntry(BaseModel):
    author: Optional[str] = Field(default="Author not found")
    post_date: Optional[str] = Field(default="Date not found")
    content: Optional[str] = Field(default="Content not found")

class StudentSubmissionData(BaseModel):
    student_id: Optional[str] = Field(default="ID not found")
    student_name: Optional[str] = Field(default="Name not found")
    entries: List[DiscussionEntry] = []
    status: Optional[str] = None
    error: Optional[str] = None
