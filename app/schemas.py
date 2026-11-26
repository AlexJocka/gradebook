"""Схемы данных REST API."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

StudyForm = Literal["full_time", "evening", "extramural"]
ControlForm = Literal["exam", "credit"]
Result = Literal["5", "4", "3", "2", "pass", "fail"]
Role = Literal["admin", "methodist", "teacher"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- справочники ---
class SpecialtyIn(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    name: str = Field(min_length=1, max_length=255)


class SpecialtyOut(ORM, SpecialtyIn):
    id: int


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    specialty_id: int


class GroupOut(ORM):
    id: int
    name: str
    specialty_id: int


class DisciplineIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class DisciplineOut(ORM, DisciplineIn):
    id: int


# --- студенты ---
class StudentIn(BaseModel):
    last_name: str = Field(min_length=1, max_length=100)
    first_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    admission_year: int = Field(ge=1990, le=2100)
    study_form: StudyForm
    group_id: int
    is_active: bool = True

    @field_validator("middle_name")
    @classmethod
    def empty_to_none(cls, v: str | None) -> str | None:
        return v or None


class StudentOut(ORM, StudentIn):
    id: int
    full_name: str


# --- учебный план ---
class CurriculumIn(BaseModel):
    specialty_id: int
    discipline_id: int
    semester: int = Field(ge=1, le=12)
    hours: int = Field(ge=1, le=1000)
    control_form: ControlForm


class CurriculumOut(ORM, CurriculumIn):
    id: int


class DisciplineHoursRow(BaseModel):
    specialty: str
    semester: int
    hours: int
    control_form: ControlForm


class DisciplineHours(BaseModel):
    discipline: str
    items: list[DisciplineHoursRow]
    total_hours: int


# --- журнал успеваемости ---
class GradeIn(BaseModel):
    academic_year: str = Field(pattern=r"^\d{4}/\d{4}$", examples=["2026/2027"])
    student_id: int
    discipline_id: int
    semester: int = Field(ge=1, le=12)
    result: Result
    graded_on: date = Field(default_factory=date.today)

    @field_validator("academic_year")
    @classmethod
    def consecutive_years(cls, v: str) -> str:
        first, second = (int(x) for x in v.split("/"))
        if second != first + 1:
            raise ValueError("учебный год должен быть вида ГГГГ/ГГГГ+1, например 2026/2027")
        return v


class GradeUpdate(BaseModel):
    result: Result
    graded_on: date = Field(default_factory=date.today)


class GradeOut(ORM):
    id: int
    academic_year: str
    student_id: int
    curriculum_item_id: int
    result: Result
    graded_on: date
    teacher_id: int | None


# --- пользователи ---
class UserIn(BaseModel):
    login: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    role: Role


class UserOut(ORM):
    id: int
    login: str
    full_name: str
    role: Role
    is_blocked: bool
