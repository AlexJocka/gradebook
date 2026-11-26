#!/bin/sh
# Подготовка БД (схема и начальные пользователи), затем запуск переданной команды
set -e

if [ "${SEED_DEMO:-false}" = "true" ]; then
  python -m app.seed --demo
else
  python -m app.seed
fi

exec "$@"
