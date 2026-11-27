"""Веб-интерфейс (Jinja2). Формы отправляются методом POST с CSRF-токеном и перенаправлением (PRG)."""

import secrets
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import schemas, services
from app.db import get_db
from app.errors import AccessDenied, NotAuthenticated
from app.models import (
    CONTROL_FORMS,
    RESULTS,
    RESULTS_BY_CONTROL_FORM,
    ROLES,
    STUDY_FORMS,
    AppUser,
    AuditLog,
    CurriculumItem,
    Discipline,
    Grade,
    Specialty,
    Student,
    StudyGroup,
)
from app.security import authenticate, require

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals.update(
    STUDY_FORMS=STUDY_FORMS,
    CONTROL_FORMS=CONTROL_FORMS,
    RESULTS=RESULTS,
    RESULTS_BY_CONTROL_FORM=RESULTS_BY_CONTROL_FORM,
    ROLES=ROLES,
)

ANY = require()
ADMIN = require("admin")
STAFF = require("admin", "methodist")
GRADERS = require("admin", "teacher")


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = request.session["csrf"] = secrets.token_urlsafe(24)
    return token


async def check_csrf(request: Request) -> None:
    form = await request.form()
    if not secrets.compare_digest(str(form.get("csrf_token", "")), request.session.get("csrf", "")):
        raise AccessDenied("Форма устарела, обновите страницу и повторите")


def flash(request: Request, message: str, kind: str = "ok") -> None:
    request.session.setdefault("flash", []).append([kind, message])


def render(request: Request, name: str, user: AppUser | None = None, **ctx) -> HTMLResponse:
    messages = request.session.pop("flash", [])
    return templates.TemplateResponse(
        request, name, {"user": user, "csrf": csrf_token(request), "messages": messages, **ctx}
    )


def back(request: Request, default: str = "/") -> RedirectResponse:
    return RedirectResponse(request.headers.get("referer") or default, status_code=303)


def _int(value: str | None) -> int | None:
    return int(value) if value not in (None, "") else None


# ---------- вход и выход ----------
@router.get("/login")
def login_page(request: Request):
    return render(request, "login.html")


@router.post("/login", dependencies=[Depends(check_csrf)])
def login(request: Request, login: str = Form(), password: str = Form(), db: Session = Depends(get_db)):
    user = authenticate(db, login, password)
    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# ---------- главная: Ф1 и Ф2 ----------
@router.get("/")
def index(
    request: Request,
    study_form: str | None = None,
    discipline_id: str | None = None,
    db: Session = Depends(get_db),
    user: AppUser = Depends(ANY),
):
    counts = None
    if user.role in ("admin", "methodist"):
        counts = services.count_students(db, study_form or None)
    hours = None
    if discipline_id:
        hours = services.discipline_hours(db, int(discipline_id))
    return render(
        request,
        "index.html",
        user,
        counts=counts,
        study_form=study_form,
        hours=hours,
        discipline_id=_int(discipline_id),
        disciplines=db.scalars(select(Discipline).order_by(Discipline.name)).all(),
    )


# ---------- Ф3. Студенты ----------
@router.get("/students")
def students_page(
    request: Request,
    group_id: str | None = None,
    study_form: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
    user: AppUser = Depends(ANY),
):
    query = select(Student).order_by(Student.last_name, Student.first_name)
    if group_id:
        query = query.where(Student.group_id == int(group_id))
    if study_form:
        query = query.where(Student.study_form == study_form)
    if q:
        query = query.where(Student.last_name.ilike(f"{q}%"))
    return render(
        request,
        "students.html",
        user,
        students=(students := db.scalars(query).all()),
        perf=services.performance(db, [s.id for s in students]),
        groups=db.scalars(select(StudyGroup).order_by(StudyGroup.name)).all(),
        filters={"group_id": _int(group_id), "study_form": study_form, "q": q or ""},
        this_year=date.today().year,
    )


def _student_form(form) -> schemas.StudentIn:
    return schemas.StudentIn(
        last_name=form.get("last_name", "").strip(),
        first_name=form.get("first_name", "").strip(),
        middle_name=form.get("middle_name", "").strip() or None,
        admission_year=_int(form.get("admission_year")),
        study_form=form.get("study_form"),
        group_id=_int(form.get("group_id")),
        is_active=form.get("is_active", "on") == "on",
    )


@router.post("/students", dependencies=[Depends(check_csrf)])
async def students_add(request: Request, db: Session = Depends(get_db), user: AppUser = Depends(STAFF)):
    student = services.create_student(db, user, _student_form(await request.form()))
    flash(request, f"Студент {student.full_name} добавлен")
    return back(request, "/students")


@router.get("/students/{student_id}")
def student_edit_page(student_id: int, request: Request, db: Session = Depends(get_db), user: AppUser = Depends(STAFF)):
    return render(
        request,
        "student_edit.html",
        user,
        s=services.get_or_404(db, Student, student_id, "Студент"),
        groups=db.scalars(select(StudyGroup).order_by(StudyGroup.name)).all(),
    )


@router.post("/students/{student_id}", dependencies=[Depends(check_csrf)])
async def student_edit(student_id: int, request: Request, db: Session = Depends(get_db), user: AppUser = Depends(STAFF)):
    form = await request.form()
    data = _student_form({**form, "is_active": "on" if form.get("is_active") else "off"})
    services.update_student(db, user, student_id, data)
    flash(request, "Изменения сохранены")
    return RedirectResponse("/students", status_code=303)


# ---------- Ф3. Учебный план ----------
@router.get("/curriculum")
def curriculum_page(
    request: Request, specialty_id: str | None = None, db: Session = Depends(get_db), user: AppUser = Depends(ANY)
):
    query = select(CurriculumItem).order_by(CurriculumItem.specialty_id, CurriculumItem.semester)
    if specialty_id:
        query = query.where(CurriculumItem.specialty_id == int(specialty_id))
    return render(
        request,
        "curriculum.html",
        user,
        items=db.scalars(query).all(),
        specialties=db.scalars(select(Specialty).order_by(Specialty.code)).all(),
        disciplines=db.scalars(select(Discipline).order_by(Discipline.name)).all(),
        specialty_id=_int(specialty_id),
    )


def _curriculum_form(form) -> schemas.CurriculumIn:
    return schemas.CurriculumIn(
        specialty_id=_int(form.get("specialty_id")),
        discipline_id=_int(form.get("discipline_id")),
        semester=_int(form.get("semester")),
        hours=_int(form.get("hours")),
        control_form=form.get("control_form"),
    )


@router.post("/curriculum", dependencies=[Depends(check_csrf)])
async def curriculum_add(request: Request, db: Session = Depends(get_db), user: AppUser = Depends(STAFF)):
    services.create_curriculum_item(db, user, _curriculum_form(await request.form()))
    flash(request, "Строка учебного плана добавлена")
    return back(request, "/curriculum")


@router.post("/curriculum/{item_id}", dependencies=[Depends(check_csrf)])
async def curriculum_edit(item_id: int, request: Request, db: Session = Depends(get_db), user: AppUser = Depends(STAFF)):
    services.update_curriculum_item(db, user, item_id, _curriculum_form(await request.form()))
    flash(request, "Строка учебного плана изменена")
    return back(request, "/curriculum")


# ---------- Ф4. Журнал успеваемости ----------
@router.get("/grades")
def grades_page(
    request: Request,
    group_id: str | None = None,
    academic_year: str | None = None,
    db: Session = Depends(get_db),
    user: AppUser = Depends(ANY),
):
    query = select(Grade).join(Grade.student).order_by(Grade.graded_on.desc(), Grade.id.desc())
    if group_id:
        query = query.where(Student.group_id == int(group_id))
    if academic_year:
        query = query.where(Grade.academic_year == academic_year)
    today = date.today()
    default_year = f"{today.year}/{today.year + 1}" if today.month >= 9 else f"{today.year - 1}/{today.year}"
    return render(
        request,
        "grades.html",
        user,
        grades=db.scalars(query.limit(500)).all(),
        groups=db.scalars(select(StudyGroup).order_by(StudyGroup.name)).all(),
        students=db.scalars(select(Student).where(Student.is_active.is_(True)).order_by(Student.last_name)).all(),
        disciplines=db.scalars(select(Discipline).order_by(Discipline.name)).all(),
        filters={"group_id": _int(group_id), "academic_year": academic_year or ""},
        default_year=default_year,
        can_edit=user.role in ("admin", "teacher"),
    )


@router.post("/grades", dependencies=[Depends(check_csrf)])
async def grades_add(request: Request, db: Session = Depends(get_db), user: AppUser = Depends(GRADERS)):
    form = await request.form()
    data = schemas.GradeIn(
        academic_year=form.get("academic_year", "").strip(),
        student_id=_int(form.get("student_id")),
        discipline_id=_int(form.get("discipline_id")),
        semester=_int(form.get("semester")),
        result=form.get("result"),
        graded_on=form.get("graded_on") or date.today(),
    )
    services.create_grade(db, user, data)
    flash(request, "Оценка выставлена")
    return back(request, "/grades")


@router.post("/grades/{grade_id}", dependencies=[Depends(check_csrf)])
async def grades_edit(grade_id: int, request: Request, db: Session = Depends(get_db), user: AppUser = Depends(GRADERS)):
    form = await request.form()
    services.update_grade(db, user, grade_id, schemas.GradeUpdate(result=form.get("result")))
    flash(request, "Оценка изменена")
    return back(request, "/grades")


# ---------- Справочники ----------
@router.get("/refs")
def refs_page(request: Request, db: Session = Depends(get_db), user: AppUser = Depends(ANY)):
    return render(
        request,
        "refs.html",
        user,
        specialties=db.scalars(select(Specialty).order_by(Specialty.code)).all(),
        groups=db.scalars(select(StudyGroup).order_by(StudyGroup.name)).all(),
        disciplines=db.scalars(select(Discipline).order_by(Discipline.name)).all(),
    )


@router.post("/refs/specialties", dependencies=[Depends(check_csrf)])
def refs_specialty(request: Request, code: str = Form(), name: str = Form(), db: Session = Depends(get_db), user: AppUser = Depends(STAFF)):
    services.create_specialty(db, user, schemas.SpecialtyIn(code=code.strip(), name=name.strip()))
    flash(request, "Специальность добавлена")
    return back(request, "/refs")


@router.post("/refs/groups", dependencies=[Depends(check_csrf)])
def refs_group(request: Request, name: str = Form(), specialty_id: int = Form(), db: Session = Depends(get_db), user: AppUser = Depends(STAFF)):
    services.create_group(db, user, schemas.GroupIn(name=name.strip(), specialty_id=specialty_id))
    flash(request, "Группа добавлена")
    return back(request, "/refs")


@router.post("/refs/disciplines", dependencies=[Depends(check_csrf)])
def refs_discipline(request: Request, name: str = Form(), db: Session = Depends(get_db), user: AppUser = Depends(STAFF)):
    services.create_discipline(db, user, schemas.DisciplineIn(name=name.strip()))
    flash(request, "Дисциплина добавлена")
    return back(request, "/refs")


# ---------- Ф5, Ф7. Администрирование ----------
@router.get("/users")
def users_page(request: Request, db: Session = Depends(get_db), user: AppUser = Depends(ADMIN)):
    return render(request, "users.html", user, users=db.scalars(select(AppUser).order_by(AppUser.login)).all())


@router.post("/users", dependencies=[Depends(check_csrf)])
def users_add(
    request: Request,
    login: str = Form(),
    password: str = Form(),
    full_name: str = Form(),
    role: str = Form(),
    db: Session = Depends(get_db),
    user: AppUser = Depends(ADMIN),
):
    services.create_user(db, user, schemas.UserIn(login=login.strip(), password=password, full_name=full_name.strip(), role=role))
    flash(request, f"Пользователь {login} создан")
    return back(request, "/users")


@router.post("/users/{user_id}/block", dependencies=[Depends(check_csrf)])
def users_block(user_id: int, request: Request, blocked: str = Form(), db: Session = Depends(get_db), user: AppUser = Depends(ADMIN)):
    services.set_user_blocked(db, user, user_id, blocked == "1")
    return back(request, "/users")


@router.get("/audit")
def audit_page(request: Request, db: Session = Depends(get_db), user: AppUser = Depends(ADMIN)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(200)).all()
    logins = {u.id: u.login for u in db.scalars(select(AppUser)).all()}
    return render(request, "audit.html", user, rows=rows, logins=logins)


def is_web_request(request: Request) -> bool:
    return not request.url.path.startswith("/api") and request.url.path not in ("/health", "/docs", "/openapi.json")


def web_error_response(request: Request, message: str, error) -> RedirectResponse:
    if isinstance(error, NotAuthenticated) and request.method == "GET":
        return RedirectResponse("/login", status_code=303)
    flash(request, message, "error")
    if request.url.path == "/login":
        return RedirectResponse("/login", status_code=303)
    return back(request)
