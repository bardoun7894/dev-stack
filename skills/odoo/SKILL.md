---
name: odoo
description: Connect the owner's apps to a client's Odoo (focus Odoo 16) through the external API, and read/audit what is in an Odoo database - installed apps, custom x_ models and fields, API user rights, record counts, stuck crons, failed mails, duplicates, draft backlog - to say what needs fixing and what needs connecting. Gap-checks an app's needed models/fields against the real Odoo, gives a Laravel JSON-RPC client with exactly-once writes, and runs a local Odoo 16 for demos and tests. Use for "odoo", "connect to odoo", "odoo api", "audit the odoo", "what is in their odoo", "sync with odoo", "odoo 16", "xmlrpc/jsonrpc", "push to odoo", "read from odoo", "odoo integration", and Darija/Arabic "أودو", "اودو", "ربط مع odoo", "شوف شنو كاين ف odoo", "شنو خاصو يتصلح ف odoo".
---

# odoo

Helper: `python3 ~/.claude/skills/odoo/scripts/odoo.py`. It is stdlib only, runs on Python 3.10+ (Mac and MyContabo), and uses JSON-RPC.
It is read-only by default. Global flags go before the command: `--profile NAME`, `--json`, `--dry-run`, `--yes`.

Read these before you build:
- `references/odoo16-api.md`: endpoints, auth, errors, methods, domains, Command tuples, verified Odoo 16 model and field names, security, hosting, what changes after 16.
- `references/laravel.md`: the `OdooGateway` contract, the JSON-RPC client, the fake for tests, exactly-once writes, sync and push patterns.
- `references/examples/fleet-intake.gap.json`: an example needs-spec for `gap`.

## Hard rules

1. The client's Odoo is their production ERP. `create`, `write`, `unlink` and any `call` to a non-read method need `--yes`.
   Before that:
   - show the `--dry-run` output to the owner and pass `--yes` only after they confirm that exact action;
   - run the first writes of any integration on a copy (Odoo.sh staging, a duplicated DB, or the local container below), never first on production;
   - create purchases and invoices as drafts unless the owner says otherwise.
2. Credentials never go in chat, briefs, logs, commits or command lines.
   - They live in `~/.config/odoo/<profile>` (chmod 600; the script refuses a group- or world-readable file) or in env vars `ODOO_URL`, `ODOO_DB`, `ODOO_USER`, `ODOO_API_KEY`.
   - If one is missing, collect it with `request_secret` (file delivery). One profile per client, e.g. `jaafar`, `amiininox`.
   - In apps, encrypt the API key at rest, never send it to an AI prompt, and never log it.
3. Use a dedicated internal integration user with only the groups the app needs, never admin. If the audit shows the user is admin, report that as a finding.
4. Every write from an app is exactly-once. Use an app-namespaced key, a lock per key, a search before create (archived included), and the same search before each retry (`laravel.md`).
5. Mark each Odoo fact you report as `audit`, `live` or `docs`. Never write a field or model name from memory into app code: run `fields MODEL` or `gap` first, because custom modules and versions rename things.
6. https only. The client refuses `http://` except to localhost; set `ODOO_ALLOW_HTTP=1` only for a private network.

## Profile file

```
# ~/.config/odoo/jaafar   (chmod 600)
ODOO_URL=https://client.odoo.com
ODOO_DB=client
ODOO_USER=api@client.ma
ODOO_API_KEY=<from Preferences > Account Security > New API Key>
# optional
ODOO_COMPANY_IDS=1,2
ODOO_LANG=fr_FR
ODOO_TIMEOUT=30
```

## Commands

```
odoo.py config                          # resolved settings, key redacted
odoo.py version                         # no login: server_version, serie
odoo.py dbs                             # db list (only if list_db is on)
odoo.py whoami                          # uid, groups, companies, admin? + findings
odoo.py modules [--apps] [--search X] [--all-states]
odoo.py models [--search fleet] [--custom]
odoo.py fields MODEL [--required] [--custom] [--search X]
odoo.py count MODEL "[('state','=','draft')]"
odoo.py read MODEL "[domain]" --fields a,b --limit 20 [--offset N] [--order "id desc"]
odoo.py get MODEL ID [ID..] [--fields a,b]
odoo.py group MODEL FIELD[:month] ["[domain]"]   # counts per value
odoo.py xmlid module.name [..]  |  xmlid MODEL ID
odoo.py access MODEL [MODEL..]          # read/write/create/unlink for the API user
odoo.py audit [--models a,b] [--sample N] [--out DIR]   # DIR/audit.md + audit.json
odoo.py gap SPEC.json                   # exit 3 when gaps are found
odoo.py create MODEL '{"name":"X"}'         --dry-run | --yes
odoo.py write MODEL 1,2 '{"name":"Y"}'      --dry-run | --yes
odoo.py unlink MODEL 1,2                    --dry-run | --yes
odoo.py call MODEL METHOD '[args]' '{kwargs}'   # read methods free, others need --yes
```

Domains accept JSON or Python literals. Pass `-` to read JSON from stdin.

## W1. Read a client's Odoo: what we have, what needs fixing

1. `version`. Unreachable, or `login failed` on a correct key: the plan may block the API. On Odoo Online the external API needs the Custom plan. That is a question for the client, not a bug.
2. `whoami`, then `audit --out ~/odoo-audits/<client>/<date>`. Write it outside any git repo: with
   `--sample N` the JSON holds the client's real records (contacts, employees). Pass `--sample 3` only
   when you need example rows to understand the data.
3. If the audit runs as the limited integration user, it reports what that user cannot read and models that show "readable but 0 records" (record rules). Ask the client admin for one admin-level audit run, or compare counts with an admin export.
4. Report to the owner with codes: `F1..Fn` from the audit's Findings, sorted high first.
   - Split them into fix (data or config problems in their Odoo) and connect (what the app must handle, such as multi-company or custom fields).
   - Add what each fix means for the client in one line.
5. Custom models and `x_` fields, and modules not by Odoo S.A., are where client-specific data lives. Read them with `fields MODEL` and `read MODEL --limit 5` before mapping.

## W2. Connect one of the owner's apps

1. Write the app's needs as a gap spec, like `references/examples/fleet-intake.gap.json`:
   - the modules it needs;
   - per model, the fields it reads or writes;
   - per model, the operations it performs (`read`, `create`, `write`).
2. `gap spec.json` reports:
   - modules not installed;
   - missing models and fields;
   - missing rights;
   - required fields with no default that your mapping does not fill.

   Fix the gaps in this order: client config (rights, module install), then the mapping, then code.
3. Store the mapping as data (`odoo_mappings`: our type to model, field map, fixed ids like the `service_type_id` for fuel). Do not hardcode it. Fixed ids come from `read` or `xmlid`.
4. Build the client from `laravel.md`: the contract, the JSON-RPC class, the fake, exactly-once with a key field. Tests use the fake. One integration test runs against the local container (W3).
5. Sync reads by `write_date` into local cache tables, so matching runs locally. Writes go through a queued job with retries.
6. First real writes go to a copy of the client's DB. Then `audit` again and diff the counts.

Odoo 16 has no outbound webhook action, and server actions cannot make HTTP calls. Poll, or ship a custom module on self-hosted or Odoo.sh only.

## W3. Local Odoo 16 for demos and tests

Mac only for a quick check. Demos and app tests run on MyContabo per where-to-work, with heavy runs through `gate-run`.

```yaml
# compose.yml
services:
  db:   {image: postgres:15-alpine, environment: {POSTGRES_USER: odoo, POSTGRES_PASSWORD: odoo, POSTGRES_DB: postgres}}
  odoo: {image: odoo:16, depends_on: [db], ports: ["127.0.0.1:18069:8069"], environment: {HOST: db, USER: odoo, PASSWORD: odoo}}
```

```
docker compose -p odoo16 up -d
docker compose -p odoo16 exec -T odoo odoo -d demo -i fleet,purchase,account,stock --stop-after-init --no-http \
  --db_host db --db_user odoo --db_password odoo          # demo data included; about 1 min
# API key for admin, written straight into the profile ~/.config/odoo/local (never printed):
mkdir -p ~/.config/odoo && umask 077 && KEY=$(echo "print(env['res.users.apikeys'].with_user(env.ref('base.user_admin'))._generate(None,'local')); env.cr.commit()" | \
  docker compose -p odoo16 exec -T odoo odoo shell -d demo --no-http --db_host db --db_user odoo --db_password odoo 2>/dev/null | tail -1) && \
  printf 'ODOO_URL=http://127.0.0.1:18069\nODOO_DB=demo\nODOO_USER=admin\nODOO_API_KEY=%s\n' "$KEY" > ~/.config/odoo/local && chmod 600 ~/.config/odoo/local
```

To test like a real limited user, create a second user with only e.g. `fleet.fleet_group_user` and audit as that user too.
Shut it down with `docker compose -p odoo16 down -v`.

## Tests

`cd ~/.claude/skills/odoo/scripts && python3 -m unittest test_odoo -v` runs offline with a fake transport. It covers the request shape, config permissions, write guards, a limited-user audit and the gap check.

## Related

- `jaafar-odoo` (`/root/jaafar-odoo`, spec `001-odoo-intake`) is the first app built on this. Its D4 `DiscoverOdoo` job is `audit` plus `gap` in app form.
- When the client asks whether to replace Odoo or extend it, that is a `system-design` decision. This skill only reads and connects.
