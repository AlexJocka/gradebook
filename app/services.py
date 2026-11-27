"""Бизнес-логика функций Ф1–Ф5. Каждая операция изменения пишет событие в журнал (Ф7)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import audit, schemas
from app.errors import (
    ControlFormLocked,
    DisciplineNotInPlan,
    DuplicateRecord,
    InvalidResult,
    NotFound,
    StudentExpelled,
)
from app.models import (
    CONTROL_FORMS,
    RESULTS,
    RESULTS_BY_CONTROL_FORM,
    STUDY_FORMS,
    AppUser,
    CurriculumItem,
    Discipline,
    Grade,
    Specialty,
    Student,
    StudyGroup,
)
from app.security import hash_password


def get_or_404(db: Session, model, obj_id: int, what: str):
    obj = db.get(model, obj_id)
    if obj is None:
        raise NotFound(f"{what} с идентификатором {obj_id} не найден(а)", entity=model.__tablename__, id=obj_id)
    return obj


def _changes(obj, data: dict) -> dict:
    """Применяет изменения к объекту и возвращает {поле: [старое, новое]} для журнала."""
    diff = {}
    for key, value in data.items():
        old = getattr(obj, key)
        if old != value:
            diff[key] = [str(old) if old is not None else None, str(value) if value is not None else None]
            setattr(obj, key, value)
    return diff


# ---------- Ф1. Количество студентов по форме обучения ----------
def count_students(
    db: Session,
    study_form: str | None = None,
    group_id: int | None = None,
    admission_year: int | None = None,
) -> dict[str, int]:
    query = select(Student.study_form, func.count()).where(Student.is_active.is_(True))
    if group_id is not None:
        query = query.where(Student.group_id == group_id)
    if admission_year is not None:
        query = query.where(Student.admission_year == admission_year)
    counts = dict.fromkeys(STUDY_FORMS, 0)
    for form, count in db.execute(query.group_by(Student.study_form)):
        counts[form] = count
    if study_form:
        return {study_form: counts.get(study_form, 0)}
    return counts


# ---------- Ф2. Часы и форма отчётности по дисциплине ----------
def discipline_hours(db: Session, discipline_id: int, specialty_id: int | None = None) -> schemas.DisciplineHours:
    discipline = get_or_404(db, Discipline, discipline_id, "Дисциплина")
    query = (
        select(CurriculumItem)
        .where(CurriculumItem.discipline_id == discipline_id)
        .order_by(CurriculumItem.specialty_id, CurriculumItem.semester)
    )
    if specialty_id is not None:
        query = query.where(CurriculumItem.specialty_id == specialty_id)
    items = db.scalars(query).all()
    rows = [
        schemas.DisciplineHoursRow(
            specialty=f"{i.specialty.code} {i.specialty.name}",
            semester=i.semester,
            hours=i.hours,
            control_form=i.control_form,
        )
        for i in items
    ]
    return schemas.DisciplineHours(discipline=discipline.name, items=rows, total_hours=sum(r.hours for r in rows))


# ---------- Справочники ----------
def create_specialty(db: Session, user: AppUser, data: schemas.SpecialtyIn) -> Specialty:
    if db.scalar(select(Specialty).where(Specialty.code == data.code)):
        raise DuplicateRecord(f"Специальность с кодом {data.code} уже существует", code=data.code)
    obj = Specialty(**data.model_dump())
    db.add(obj)
    db.flush()
    audit.write(db, user, "create", "specialty", obj.id, data.model_dump())
    db.commit()
    return obj


def create_group(db: Session, user: AppUser, data: schemas.GroupIn) -> StudyGroup:
    get_or_404(db, Specialty, data.specialty_id, "Специальность")
    if db.scalar(select(StudyGroup).where(StudyGroup.name == data.name)):
        raise DuplicateRecord(f"Группа {data.name} уже существует", name=data.name)
    obj = StudyGroup(**data.model_dump())
    db.add(obj)
    db.flush()
    audit.write(db, user, "create", "study_group", obj.id, data.model_dump())
    db.commit()
    return obj


def create_discipline(db: Session, user: AppUser, data: schemas.DisciplineIn) -> Discipline:
    if db.scalar(select(Discipline).where(Discipline.name == data.name)):
        raise DuplicateRecord(f"Дисциплина «{data.name}» уже существует", name=data.name)
    obj = Discipline(**data.model_dump())
    db.add(obj)
    db.flush()
    audit.write(db, user, "create", "discipline", obj.id, data.model_dump())
    db.commit()
    return obj


# ---------- Ф3. Студенты ----------
def create_student(db: Session, user: AppUser, data: schemas.StudentIn) -> Student:
    get_or_404(db, StudyGroup, data.group_id, "Группа")
    obj = Student(**data.model_dump())
    db.add(obj)
    db.flush()
    audit.write(db, user, "create", "student", obj.id, data.model_dump())
    db.commit()
    return obj


def update_student(db: Session, user: AppUser, student_id: int, data: schemas.StudentIn) -> Student:
    obj = get_or_404(db, Student, student_id, "Студент")
    get_or_404(db, StudyGroup, data.group_id, "Группа")
    diff = _changes(obj, data.model_dump())
    if diff:
        audit.write(db, user, "update", "student", obj.id, diff)
    db.commit()
    return obj


# ---------- Ф3. Учебный план ----------
def create_curriculum_item(db: Session, user: AppUser, data: schemas.CurriculumIn) -> CurriculumItem:
    get_or_404(db, Specialty, data.specialty_id, "Специальность")
    get_or_404(db, Discipline, data.discipline_id, "Дисциплина")
    exists = db.scalar(
        select(CurriculumItem).where(
            CurriculumItem.specialty_id == data.specialty_id,
            CurriculumItem.discipline_id == data.discipline_id,
            CurriculumItem.semester == data.semester,
        )
    )
    if exists:
        raise DuplicateRecord(
            "Эта дисциплина уже есть в учебном плане специальности в указанном семестре", id=exists.id
        )
    obj = CurriculumItem(**data.model_dump())
    db.add(obj)
    db.flush()
    audit.write(db, user, "create", "curriculum_item", obj.id, data.model_dump())
    db.commit()
    return obj


def update_curriculum_item(db: Session, user: AppUser, item_id: int, data: schemas.CurriculumIn) -> CurriculumItem:
    obj = get_or_404(db, CurriculumItem, item_id, "Строка учебного плана")
    if data.control_form != obj.control_form:
        grades = db.scalar(select(func.count()).select_from(Grade).where(Grade.curriculum_item_id == obj.id))
        if grades:
            raise ControlFormLocked(
                f"Нельзя сменить форму отчётности: по этой строке плана уже выставлено оценок: {grades}",
                grades=grades,
            )
    diff = _changes(obj, data.model_dump())
    if diff:
        audit.write(db, user, "update", "curriculum_item", obj.id, diff)
    db.commit()
    return obj


# ---------- Ф4. Журнал успеваемости ----------
def _check_result(item: CurriculumItem, result: str) -> None:
    allowed = RESULTS_BY_CONTROL_FORM[item.control_form]
    if result not in allowed:
        raise InvalidResult(
            f"Для формы отчётности «{CONTROL_FORMS[item.control_form]}» допустимы оценки: "
            + ", ".join(RESULTS[r] for r in allowed),
            allowed=list(allowed),
        )


def create_grade(db: Session, user: AppUser, data: schemas.GradeIn) -> Grade:
    student = get_or_404(db, Student, data.student_id, "Студент")
    get_or_404(db, Discipline, data.discipline_id, "Дисциплина")
    if not student.is_active:
        raise StudentExpelled(f"Студент {student.full_name} отчислен, выставление оценок невозможно")
    item = db.scalar(
        select(CurriculumItem).where(
            CurriculumItem.specialty_id == student.group.specialty_id,
            CurriculumItem.discipline_id == data.discipline_id,
            CurriculumItem.semester == data.semester,
        )
    )
    if item is None:
        raise DisciplineNotInPlan(
            f"Дисциплины нет в учебном плане специальности {student.group.specialty.code} "
            f"в {data.semester} семестре",
            specialty_id=student.group.specialty_id,
            semester=data.semester,
        )
    _check_result(item, data.result)
    duplicate = db.scalar(
        select(Grade).where(Grade.student_id == student.id, Grade.curriculum_item_id == item.id)
    )
    if duplicate:
        raise DuplicateRecord(
            "Оценка по этой дисциплине и семестру уже выставлена, измените существующую запись",
            grade_id=duplicate.id,
        )
    obj = Grade(
        academic_year=data.academic_year,
        student_id=student.id,
        curriculum_item_id=item.id,
        result=data.result,
        graded_on=data.graded_on,
        teacher_id=user.id,
    )
    db.add(obj)
    db.flush()
    audit.write(db, user, "create", "grade", obj.id, data.model_dump(mode="json"))
    db.commit()
    return obj


def update_grade(db: Session, user: AppUser, grade_id: int, data: schemas.GradeUpdate) -> Grade:
    obj = get_or_404(db, Grade, grade_id, "Запись журнала")
    if not obj.student.is_active:
        raise StudentExpelled(f"Студент {obj.student.full_name} отчислен, изменение оценок невозможно")
    _check_result(obj.curriculum_item, data.result)
    diff = _changes(obj, data.model_dump())
    if diff:
        obj.teacher_id = user.id
        audit.write(db, user, "update", "grade", obj.id, diff)
    db.commit()
    return obj


# ---------- Средний балл и задолженности ----------
EXAM_MARKS = ("5", "4", "3", "2")
DEBT_RESULTS = ("2", "fail")


def performance(db: Session, student_ids: list[int] | None = None) -> dict[int, dict]:
    """Средний балл по экзаменам, число экзаменов, зачётов и задолженностей для каждого студента."""
    query = select(Grade.student_id, Grade.result)
    if student_ids is not None:
        if not student_ids:
            return {}
        query = query.where(Grade.student_id.in_(student_ids))
    stats: dict[int, dict] = {}
    for student_id, result in db.execute(query):
        s = stats.setdefault(student_id, {"marks": [], "credits_passed": 0, "debts": 0})
        if result in EXAM_MARKS:
            s["marks"].append(int(result))
        elif result == "pass":
            s["credits_passed"] += 1
        if result in DEBT_RESULTS:
            s["debts"] += 1
    return {
        sid: {
            "average": round(sum(s["marks"]) / len(s["marks"]), 2) if s["marks"] else None,
            "exams": len(s["marks"]),
            "credits_passed": s["credits_passed"],
            "debts": s["debts"],
        }
        for sid, s in stats.items()
    }


def student_summary(db: Session, student_id: int) -> schemas.StudentSummary:
    student = get_or_404(db, Student, student_id, "Студент")
    data = performance(db, [student_id]).get(student_id, {"average": None, "exams": 0, "credits_passed": 0, "debts": 0})
    return schemas.StudentSummary(student_id=student.id, full_name=student.full_name, group=student.group.name, **data)


# ---------- Ф5. Пользователи ----------
def create_user(db: Session, user: AppUser | None, data: schemas.UserIn) -> AppUser:
    if db.scalar(select(AppUser).where(AppUser.login == data.login)):
        raise DuplicateRecord(f"Пользователь {data.login} уже существует", login=data.login)
    obj = AppUser(
        login=data.login,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
        role=data.role,
    )
    db.add(obj)
    db.flush()
    audit.write(db, user, "create", "app_user", obj.id, {"login": data.login, "role": data.role})
    db.commit()
    return obj


def set_user_blocked(db: Session, user: AppUser, target_id: int, blocked: bool) -> AppUser:
    obj = get_or_404(db, AppUser, target_id, "Пользователь")
    obj.is_blocked = blocked
    audit.write(db, user, "block" if blocked else "unblock", "app_user", obj.id)
    db.commit()
    return obj
