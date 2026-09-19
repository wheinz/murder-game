# Murder Game

An assassin-style party game for a weekend away: everyone gets a target, a weapon, and a
location, and you "kill" your target by getting them to accept your weapon at your
location (e.g. a ketchup bottle at the pool). Once a kill is confirmed you inherit your
victim's contract — their target and their weapons and locations. The organiser can also
hand out bonus weapons and locations during the hunt. Last one standing wins.

Everything is fictional. The app has just three tabs: **Game** (your contract, the
roster, and the standings), **Feed** (every kill and announcement), and **Photos**.

## Stack

- Python 3.13 + [uv](https://docs.astral.sh/uv/), Django 6
- HTMX + Alpine.js (CDN), plain CSS (`static/css/app.css`)
- SQLite (WAL mode), WhiteNoise for static files, Caddy for uploaded media
- Docker Compose + Caddy for production

## How the game works

1. You (the organiser) create a game in the Django admin. It gets a random **6-digit entry
   code**.
2. Friends open the site, enter the code, and pick a nickname (unique within the game).
3. Everyone submits weapons and locations to a shared pool.
4. You start the hunt from the Django admin. The app shuffles players into one circular
   chain and deals each player a target, a weapon, and a location (avoiding your own
   submissions).
5. A kill can be opened by either side. The other party confirms or denies it. Confirming
   shows the exact contract being claimed ("did they hand you X at Y?").
6. On confirmation the victim is out and the killer takes over the victim's contract.
   If that leaves a single player, the game ends and the winner is shown.
7. At any time during an active hunt you can use the "Grant bonus weapon & location"
   admin action to give every active contract an extra weapon/location pair. It is
   repeatable and the pairs transfer along with the contract on a kill.

Players can read a plain-language version in the app at `/t/<code>/rules/`, linked from
the game page and the join screen.

## Local development

```bash
uv sync
cp .env.example .env          # then put a real SECRET_KEY in it
uv run manage.py migrate
uv run manage.py createsuperuser
uv run manage.py runserver
```

Create a game at http://127.0.0.1:8000/admin/ (Games → Add). Then visit
http://127.0.0.1:8000/ and enter its code. Start the game later with the
"Start the hunt" admin action.

Run the checks:

```bash
uv run ruff format --check
uv run ruff check
uv run pytest
```

## Production (VPS + Docker Compose)

Caddy terminates TLS and proxies to Gunicorn; SQLite and media live on a bind mount in
`./data` so they survive rebuilds.

### 1. Get a hostname

You do not need to own a domain for a temporary URL:

- `sslip.io`: any `IP` becomes `<ip>.sslip.io` (e.g. `203.0.113.5.sslip.io`).
- DuckDNS: register `<name>.duckdns.org` and point it at the VPS.

Make sure ports 80 and 443 are open (Caddy needs 80 for the ACME challenge).

### 2. Configure

```bash
git clone <this repo> trip-hq && cd trip-hq
cp .env.example .env
```

Edit `.env`:

```
SECRET_KEY=<generate one>
DEBUG=False
ALLOWED_HOSTS=murder.203.0.113.5.sslip.io
CSRF_TRUSTED_ORIGINS=https://murder.203.0.113.5.sslip.io
SITE_ADDRESS=murder.203.0.113.5.sslip.io
```

Generate a key with:

```bash
uv run python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 3. Run

```bash
mkdir -p data
docker compose up -d --build
docker compose logs -f caddy   # watch for the certificate being issued
```

Migrations run automatically on start. Visit `https://<SITE_ADDRESS>/`.

Create your operator account and a game:

```bash
docker compose exec web python manage.py createsuperuser
# then visit https://<SITE_ADDRESS>/admin/
```

### 4. Operate

```bash
docker compose ps
docker compose logs -f web
docker compose restart web
docker compose down            # stop (keeps ./data)
```

Back up everything by copying `./data` (SQLite database plus uploaded photos).

### 5. Tear down after the trip

```bash
docker compose down
rm -rf data caddy_data caddy_config   # optional: nuke the database and photos
```

## Notes and tradeoffs

- Identity is a signed session cookie set when you enter the code and pick a nickname.
  Returning to `/` sends you straight back to your game, so players do not need to
  remember the code. A nickname is permanent once chosen — there is no in-app switch — and
  duplicate nicknames are rejected, so a lost session (cleared cookies/new browser) means
  the organiser has to remove that player in the Django admin before they can rejoin.
  Anyone who knows the 6-digit code can join. There is no attempt throttling (by choice),
   so it is fine for a friends' weekend, not for anything sensitive.
- Staff can inspect any player's view without joining as them. In the Django admin
  (`/admin/core/player/`) each row has a **Log in as** button; clicking it makes your
  browser browse the app as that player, with an amber banner and an **Exit** link to
  return to the admin. It is staff-only, never touches the player's own session, and is
  purely for testing (no extra account needed). Only the impersonating browser's session
  is affected — the player's phone stays signed in.
- The game lives at `/t/<code>/`. Everything administrative lives in the Django admin:
  creating games, starting/resetting/ending the hunt, editing the pool, posting/pinning
  feed announcements, and deleting photos. Kill reports can also be confirmed or denied
  there (`/admin/game/killattempt/` → select → *Confirm/Deny selected kills*), which is
  handy for settling disputes or testing. The feed is read-only for players (auto events
  plus organiser announcements). The player-facing app is read-only except for pool
  submissions, kill record/confirm, and photo uploads.
- Resetting a game starts a new **round** (`game_number`). Kills, assignments and kill
  reports are tagged with the round they belong to, so resetting revives everyone and the
  new round starts with a clean slate. Previous rounds are preserved and can be inspected in
  the Django admin (`game_number` filters), but never show up in the app's stats. The feed
  keeps the full history, and the weapon/location pool carries over between rounds.
- The app is multi-game capable (URLs are scoped by the game's code), but it is built for a
  single weekend game at a time.
