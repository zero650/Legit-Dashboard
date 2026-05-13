#!/bin/sh
set -e

if [ "$DJANGO_DATABASE" != "sqlite" ]; then
  echo "Waiting for PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
  while ! nc -z "$POSTGRES_HOST" "$POSTGRES_PORT"; do
    sleep 1
  done
fi

python manage.py migrate --noinput
python manage.py seed_legit_defaults
python manage.py collectstatic --noinput

if [ "$DJANGO_CREATE_SUPERUSER" = "1" ] && [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py shell -c "import os; from django.contrib.auth import get_user_model; User = get_user_model(); email = os.environ.get('DJANGO_SUPERUSER_EMAIL') or os.environ['DJANGO_SUPERUSER_USERNAME']; password = os.environ['DJANGO_SUPERUSER_PASSWORD']; User.objects.filter(email=email).exists() or User.objects.create_superuser(email, password)"
fi

exec "$@"
