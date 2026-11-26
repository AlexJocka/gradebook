"""Модель данных (приложение Б технического задания)."""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Справочники перечислимых значений: код в БД -> подпись в интерфейсе
STUDY_FORMS = {"full_time": "дневная", "evening": "вечерняя", "extramural": "заочная"}
CONTROL_FORMS = {"exam": "экзамен", "credit": "зачёт"}
RESULTS = {
    "5": "отлично",
    "4": "хорошо",
    "3": "удовлетворительно",
    "2": "неудовлетворительно",
    "pass": "зачтено",
    "fail": "не зачтено",
}
RESULTS_BY_CONTROL_FORM = {"exam": ("5", "4", "3", "2"), "credit": ("pass", "fail")}
ROLES = {"admin": "администратор", "methodist": "методист", "teacher": "преподаватель"}


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


class Specialty(Base):
    __tablename__ = "specialty"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(255))


class StudyGroup(Base):
    __tablename__ = "study_group"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)
    specialty_id: Mapped[int] = mapped_column(ForeignKey("specialty.id"))

    specialty: Mapped[Specialty] = relationship(lazy="joined")


class Student(Base):
    __tablename__ = "student"
    __table_args__ = (
        CheckConstraint(_in("study_form", STUDY_FORMS), name="ck_student_study_form"),
        CheckConstraint("admission_year BETWEEN 1990 AND 2100", name="ck_student_admission_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_name: Mapped[str] = mapped_column(String(100))
    first_name: Mapped[str] = mapped_column(String(100))
    middle_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    admission_year: Mapped[int] = mapped_column(SmallInteger)
    study_form: Mapped[str] = mapped_column(String(16))
    group_id: Mapped[int] = mapped_column(ForeignKey("study_group.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    group: Mapped[StudyGroup] = relationship(lazy="joined")

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.last_name, self.first_name, self.middle_name) if p)


class Discipline(Base):
    __tablename__ = "discipline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)


class CurriculumItem(Base):
    __tablename__ = "curriculum_item"
    __table_args__ = (
        UniqueConstraint("specialty_id", "discipline_id", "semester", name="uq_curriculum_item"),
        CheckConstraint("semester BETWEEN 1 AND 12", name="ck_curriculum_semester"),
        CheckConstraint("hours BETWEEN 1 AND 1000", name="ck_curriculum_hours"),
        CheckConstraint(_in("control_form", CONTROL_FORMS), name="ck_curriculum_control_form"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    specialty_id: Mapped[int] = mapped_column(ForeignKey("specialty.id"))
    discipline_id: Mapped[int] = mapped_column(ForeignKey("discipline.id"))
    semester: Mapped[int] = mapped_column(SmallInteger)
    hours: Mapped[int] = mapped_column(SmallInteger)
    control_form: Mapped[str] = mapped_column(String(8))

    specialty: Mapped[Specialty] = relationship(lazy="joined")
    discipline: Mapped[Discipline] = relationship(lazy="joined")


class AppUser(Base):
    __tablename__ = "app_user"
    __table_args__ = (CheckConstraint(_in("role", ROLES), name="ck_app_user_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    login: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Grade(Base):
    __tablename__ = "grade"
    __table_args__ = (
        UniqueConstraint("student_id", "curriculum_item_id", name="uq_grade_student_item"),
        CheckConstraint(_in("result", RESULTS), name="ck_grade_result"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    academic_year: Mapped[str] = mapped_column(String(9))
    student_id: Mapped[int] = mapped_column(ForeignKey("student.id"))
    curriculum_item_id: Mapped[int] = mapped_column(ForeignKey("curriculum_item.id"))
    result: Mapped[str] = mapped_column(String(8))
    graded_on: Mapped[date] = mapped_column(Date)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)

    student: Mapped[Student] = relationship(lazy="joined")
    curriculum_item: Mapped[CurriculumItem] = relationship(lazy="joined")
    teacher: Mapped[AppUser | None] = relationship(lazy="joined")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(32))
    entity: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
