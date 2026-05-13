# Legit Dashboard

Django + PostgreSQL dashboard for Legit Trips group travel operations and customer management.

The app has two top-level work areas: trip/task operations and CRM.

## What is included

- PostgreSQL-backed Django project
- Staff login, trip dashboard, trip list/detail, and create/edit forms
- Email-only user accounts with no username field
- Django admin configuration for trips, statuses, employees, role groups, and tasks
- Updatable trip statuses
- Reusable task templates that generate per-trip tasks and due dates
- Employee profiles connected to Django users
- Django Groups presented as Roles for permission levels
- Permission matrix admin page for updating role permissions with checkboxes
- Starter permission groups through a seed command
- CRM for customer profiles, passport details, trip history, spend tracking, notes, and attached PDFs/images

## Project Management Models

- `Trip`: name, dates, manager, status, rich-text-ready notes, leader, and linked tasks
- `Task`: trip link, assignee, status, notes, due date, and signed day-offset scheduling
- `TaskTemplate`: reusable task checklist item with default notes and signed day-offset timing
- `Employee`: profile for a Django user
- `Group`: Django's built-in permission group, shown as Roles in the Authentication admin section
- `TripStatus`: editable list of trip lifecycle statuses

## CRM Models

- `Customer`: first name, last name, email, phone number, address, city, state, postal code, passport number, passport expiration date, and notes
- `CustomerTripHistory`: customer-linked trip name, trip start date, trip end date, and money spent
- `CustomerDocument`: customer-linked PDF/image attachments with optional titles and notes

## Permissions Approach

Django already has a strong permission system, so this app uses:

- `User` for email-based login credentials
- `Employee` for staff profile details
- `Group` for role names and permission assignment, shown as Roles under Authentication
- Django model permissions for add/change/delete/view access

Starter groups:

- `Operations Manager`: manage employees, roles, statuses, trips, and tasks
- `Trip Manager`: manage trips and assign/complete tasks
- `Staff`: view trips and manage/complete assigned task work

## Docker Setup

Start the full app and database:

```bash
docker compose up --build
```

Open https://localhost.

Docker runs Caddy in front of Django so local traffic goes through HTTPS. The local certificate is issued by Caddy's internal CA, so your browser may ask you to accept or trust the certificate the first time.

To test from an iPhone on the same Wi-Fi network, set `SITE_HOST` and `DJANGO_ALLOWED_HOSTS` to your Mac's local network name or LAN IP, then open the HTTPS URL for that host.

The development container creates a starter admin user automatically:

```text
Email: admin@example.com
Password: admin
```

On startup, the web container waits for PostgreSQL, runs migrations, seeds the default statuses and permission groups, collects static files, and starts Django.

PostgreSQL is only exposed inside the Docker network by default, so it will not conflict with another local Postgres running on your Mac.

For a public domain, point DNS at the host, set `SITE_HOST` to the domain, set `DJANGO_ALLOWED_HOSTS` to the same domain, and set `DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.com`. Caddy will use a publicly trusted certificate when the domain is reachable from the internet.

Task templates can be managed at `/task-templates/`. Open a trip and use **Apply task templates** to create that trip's own task records with calculated due dates. Negative day offsets are before the trip starts; positive offsets are after the trip starts.

Customer records can be managed at `/crm/`. Open a customer profile to track trip history and money spent, or attach PDFs and images such as passport scans, IDs, waivers, invoices, or other travel documents. Use `/crm/customers/import/` to import customers from CSV; first name, last name, and email are required, and existing customers are updated by matching email address.

Useful Docker commands:

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py test
docker compose down
docker compose down -v
```

Use `docker compose down -v` only when you want to delete the local PostgreSQL data volume.

## Manual Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d db
python manage.py migrate
python manage.py seed_legit_defaults
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000 and log in with the superuser when running Django directly without Caddy. Use the Docker setup for HTTPS.

## Useful Commands

Run checks:

```bash
python manage.py check
```

Run tests without PostgreSQL:

```bash
DJANGO_DATABASE=sqlite python manage.py test
```

Run against PostgreSQL:

```bash
docker compose up -d db
python manage.py migrate
```

## Notes

Trip and task notes are stored as text fields that can hold HTML from a rich text editor. The next sensible step is to add a polished editor widget, such as TipTap or TinyMCE, to the staff forms once the frontend stack is chosen.
