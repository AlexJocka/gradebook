"""REST API (Ф8). Права доступа соответствуют таблице 4 ТЗ."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas, services
from app.db import get_db
from app.models import AppUser, AuditLog, CurriculumItem, Discipline, Grade, Specialty, Student, StudyGroup
from app.security import require

router = APIRouter(prefix="/api", tags=["api"])

ANY = require()
ADMIN = require("admin")
STAFF = require("admin", "methodist")
GRADERS = require("admin", "teacher")


# Ф1
@router.get("/stats/students", summary="Ф1. Количество студентов по форме обучения")
def students_count(
    study_form: schemas.StudyForm | None = None,
    group_id: int | None = None,
    admission_year: int | None = None,
    db: Session = Depends(get_db),
    _: AppUser = Depends(STAFF),
) -> dict[str, int]:
    return services.count_students(db, study_form, group_id, admission_year)


# Ф2
@router.get(
    "/disciplines/{discipline_id}/hours",
    response_model=schemas.DisciplineHours,
    summary="Ф2. Часы и форма отчётности по дисциплине",
)
def discipline_hours(
    discipline_id: int,
    specialty_id: int | None = None,
    db: Session = Depends(get_db),
    _: AppUser = Depends(ANY),
):
    return services.discipline_hours(db, discipline_id, specialty_id)


# Справочники
@router.get("/specialties", response_model=list[schemas.SpecialtyOut])
def list_specialties(db: Session = Depends(get_db), _: AppUser = Depends(ANY)):
    return db.scalars(select(Specialty).order_by(Specialty.code)).all()


@router.post("/specialties", response_model=schemas.SpecialtyOut, status_code=201)
def add_specialty(data: schemas.SpecialtyIn, db: Session = Depends(get_db), user: AppUser = Depends(STAFF)):
    return services.create_specialty(db, user, data)


@router.get("/groups", response_model=list[schemas.GroupOut])
def list_groups(db: Session = Depends(get_db), _: AppUser = Depends(ANY)):
    return db.scalars(select(StudyGroup).order_by(StudyGroup.name)).all()


@router.post("/groups", response_model=schemas.GroupOut, status_code=201)
def add_group(data: schemas.GroupIn, db: Session = Depends(get_db), user: AppUser = Depends(STAFF)):
    return services.create_group(db, user, data)


@router.get("/disciplines", response_model=list[schemas.DisciplineOut])
def list_disciplines(
    q: str | None = Query(default=None, description="Поиск по части названия"),
    db: Session = Depends(get_db),
    _: AppUser = Depends(ANY),
):
    query = select(Discipline).order_by(Discipline.name)
    if q:
        query = query.where(Discipline.name.ilike(f"%{q}%"))
    return db.scalars(query).all()


@router.post("/disciplines", response_model=schemas.DisciplineOut, status_code=201)
def add_discipline(data: schemas.DisciplineIn, db: Session = Depends(get_db), user: AppUser = Depends(STAFF)):
    return services.create_discipline(db, user, data)


# Ф3. Студенты
@router.get("/students", response_model=list[schemas.StudentOut])
def list_students(
    group_id: int | None = None,
    study_form: schemas.StudyForm | None = None,
    q: str | None = Query(default=None, description="Поиск по фамилии"),
    db: Session = Depends(get_db),
    _: AppUser = Depends(ANY),
):
    query = select(Student).order_by(Student.last_name, Student.first_name)
    if group_id is not None:
        query = query.where(Student.group_id == group_id)
    if study_form:
        query = query.where(Student.study_form == study_form)
    if q:
        query = query.where(Student.last_name.ilike(f"{q}%"))
    return db.scalars(query).all()


@router.post("/students", response_model=schemas.StudentOut, status_code=201)
def add_student(data: schemas.StudentIn, db: Session = Depends(get_db), user: AppUser = Depends(STAFF)):
    return services.create_student(db, user, data)


@router.put("/students/{student_id}", response_model=schemas.StudentOut)
def edit_student(
    student_id: int, data: schemas.StudentIn, db: Session = Depends(get_db), user: AppUser = Depends(STAFF)
):
    return services.update_student(db, user, student_id, data)


# Ф3. Учебный план
@router.get("/curriculum", response_model=list[schemas.CurriculumOut])
def list_curriculum(specialty_id: int | None = None, db: Session = Depends(get_db), _: AppUser = Depends(ANY)):
    query = select(CurriculumItem).order_by(CurriculumItem.specialty_id, CurriculumItem.semester)
    if specialty_id is not None:
        query = query.where(CurriculumItem.specialty_id == specialty_id)
    return db.scalars(query).all()


@router.post("/curriculum", response_model=schemas.CurriculumOut, status_code=201)
def add_curriculum(data: schemas.CurriculumIn, db: Session = Depends(get_db), user: AppUser = Depends(STAFF)):
    return services.create_curriculum_item(db, user, data)


@router.put("/curriculum/{item_id}", response_model=schemas.CurriculumOut)
def edit_curriculum(
    item_id: int, data: schemas.CurriculumIn, db: Session = Depends(get_db), user: AppUser = Depends(STAFF)
):
    return services.update_curriculum_item(db, user, item_id, data)


# Ф4. Журнал успеваемости
@router.get("/grades", response_model=list[schemas.GradeOut])
def list_grades(
    student_id: int | None = None,
    academic_year: str | None = None,
    db: Session = Depends(get_db),
    _: AppUser = Depends(ANY),
):
    query = select(Grade).order_by(Grade.graded_on.desc(), Grade.id.desc())
    if student_id is not None:
        query = query.where(Grade.student_id == student_id)
    if academic_year:
        query = query.where(Grade.academic_year == academic_year)
    return db.scalars(query).all()


@router.post("/grades", response_model=schemas.GradeOut, status_code=201)
def add_grade(data: schemas.GradeIn, db: Session = Depends(get_db), user: AppUser = Depends(GRADERS)):
    return services.create_grade(db, user, data)


@router.put("/grades/{grade_id}", response_model=schemas.GradeOut)
def edit_grade(
    grade_id: int, data: schemas.GradeUpdate, db: Session = Depends(get_db), user: AppUser = Depends(GRADERS)
):
    return services.update_grade(db, user, grade_id, data)


# Ф5. Пользователи
@router.get("/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db), _: AppUser = Depends(ADMIN)):
    return db.scalars(select(AppUser).order_by(AppUser.login)).all()


@router.post("/users", response_model=schemas.UserOut, status_code=201)
def add_user(data: schemas.UserIn, db: Session = Depends(get_db), user: AppUser = Depends(ADMIN)):
    return services.create_user(db, user, data)


@router.post("/users/{user_id}/block", response_model=schemas.UserOut)
def block_user(user_id: int, blocked: bool = True, db: Session = Depends(get_db), user: AppUser = Depends(ADMIN)):
    return services.set_user_blocked(db, user, user_id, blocked)


# Ф7. Журнал событий
@router.get("/audit")
def list_audit(limit: int = Query(default=100, le=1000), db: Session = Depends(get_db), _: AppUser = Depends(ADMIN)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)).all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at,
            "user_id": r.user_id,
            "action": r.action,
            "entity": r.entity,
            "entity_id": r.entity_id,
            "details": r.details,
        }
        for r in rows
    ]
