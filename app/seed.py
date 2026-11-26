"""Начальное заполнение БД.

    python -m app.seed            # создать администратора (если его нет)
    python -m app.seed --demo     # плюс демонстрационные данные и пользователи methodist, teacher

Пароли берутся из переменных окружения ADMIN_PASSWORD и DEMO_PASSWORD.
Если переменная не задана, пароль генерируется и выводится в консоль один раз.
"""

import os
import secrets
import sys
from datetime import date

from sqlalchemy import select

from app import schemas, services
from app.db import SessionLocal, engine
from app.models import AppUser, Base, Specialty


def _password(env_name: str) -> tuple[str, bool]:
    value = os.getenv(env_name)
    return (value, False) if value else (secrets.token_urlsafe(9), True)


def ensure_user(db, login: str, full_name: str, role: str, env_name: str) -> AppUser:
    user = db.scalar(select(AppUser).where(AppUser.login == login))
    if user:
        return user
    password, generated = _password(env_name)
    user = services.create_user(db, None, schemas.UserIn(login=login, password=password, full_name=full_name, role=role))
    if generated:
        print(f"Создан пользователь {login}, пароль: {password}")
    else:
        print(f"Создан пользователь {login}, пароль из {env_name}")
    return user


def demo(db, admin: AppUser) -> None:
    if db.scalar(select(Specialty)):
        print("Демонстрационные данные уже есть, пропускаю")
        return
    ensure_user(db, "methodist", "Сидорова Анна Петровна", "methodist", "DEMO_PASSWORD")
    teacher = ensure_user(db, "teacher", "Кузнецов Игорь Олегович", "teacher", "DEMO_PASSWORD")

    sp1 = services.create_specialty(db, admin, schemas.SpecialtyIn(code="09.03.01", name="Информатика и вычислительная техника"))
    sp2 = services.create_specialty(db, admin, schemas.SpecialtyIn(code="09.03.04", name="Программная инженерия"))
    groups = {
        "241-321": sp1.id,
        "241-326": sp1.id,
        "241-331": sp2.id,
    }
    group_ids = {name: services.create_group(db, admin, schemas.GroupIn(name=name, specialty_id=sp)).id for name, sp in groups.items()}

    names = ["Математический анализ", "Программирование на Python", "Базы данных", "Иностранный язык", "Физическая культура"]
    disc = {n: services.create_discipline(db, admin, schemas.DisciplineIn(name=n)).id for n in names}

    plan = [
        ("Математический анализ", 1, 144, "exam"),
        ("Программирование на Python", 1, 108, "exam"),
        ("Иностранный язык", 1, 72, "credit"),
        ("Физическая культура", 1, 36, "credit"),
        ("Базы данных", 3, 144, "exam"),
        ("Математический анализ", 2, 108, "exam"),
    ]
    for sp in (sp1.id, sp2.id):
        for name, sem, hours, form in plan:
            services.create_curriculum_item(
                db, admin, schemas.CurriculumIn(specialty_id=sp, discipline_id=disc[name], semester=sem, hours=hours, control_form=form)
            )

    people = [
        ("Иванов", "Пётр", "Сергеевич", "full_time", "241-321"),
        ("Смирнова", "Мария", "Андреевна", "full_time", "241-321"),
        ("Козлов", "Дмитрий", None, "evening", "241-326"),
        ("Новикова", "Екатерина", "Игоревна", "full_time", "241-326"),
        ("Морозов", "Артём", "Викторович", "extramural", "241-331"),
        ("Волкова", "Анастасия", "Денисовна", "extramural", "241-331"),
    ]
    students = []
    for last, first, middle, form, group in people:
        students.append(
            services.create_student(
                db,
                admin,
                schemas.StudentIn(last_name=last, first_name=first, middle_name=middle, admission_year=2024, study_form=form, group_id=group_ids[group]),
            )
        )

    for s, (math, py, lang) in zip(students, [("5", "4", "pass"), ("4", "5", "pass"), ("3", "4", "fail"), ("5", "5", "pass")]):
        for name, result in (("Математический анализ", math), ("Программирование на Python", py), ("Иностранный язык", lang)):
            services.create_grade(
                db,
                teacher,
                schemas.GradeIn(academic_year="2024/2025", student_id=s.id, discipline_id=disc[name], semester=1, result=result, graded_on=date(2025, 1, 20)),
            )
    print("Демонстрационные данные добавлены")


def main(argv: list[str]) -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        admin = ensure_user(db, "admin", "Администратор системы", "admin", "ADMIN_PASSWORD")
        if "--demo" in argv:
            demo(db, admin)


if __name__ == "__main__":
    main(sys.argv[1:])
