# Odoo 16 external API reference

Sources: official 16.0 docs ([external API](https://www.odoo.com/documentation/16.0/developer/reference/external_api.html),
[ORM](https://www.odoo.com/documentation/16.0/developer/reference/backend/orm.html),
[security](https://www.odoo.com/documentation/16.0/developer/reference/backend/security.html)) and a live
`odoo:16` container (16.0-20250909) checked on 2026-11-18. "Live" marks facts checked against that
container or its source. "UNVERIFIED" marks claims with no confirmed source.

## 1. Endpoints and auth

| Endpoint | Use |
|---|---|
| `POST /jsonrpc` | JSON-RPC 2.0, `{"jsonrpc":"2.0","method":"call","params":{"service":S,"method":M,"args":[...]},"id":n}` (live) |
| `/xmlrpc/2/common` | `version()`, `authenticate(db, login, key, {})` returns uid or `false` |
| `/xmlrpc/2/object` | `execute_kw(db, uid, key, model, method, args, kwargs)` |
| `/xmlrpc/2/db` | `list()` and the other db functions |

The JSON-RPC services are the same three: `common`, `object`, `db`. The skill's CLI uses JSON-RPC. Two
reasons. First, XML-RPC responses are marshalled with `allow_none=False` (live: `base/controllers/rpc.py`),
so a method that returns `None` fails over XML-RPC. Many `action_*` and `button_*` methods return None.
Second, JSON is easier from PHP and JS.

- API key: the user opens Preferences, then Account Security, then New API Key. The key goes in the
  password slot, and the login stays the same. It is shown once and has the same rights as the user. It
  cannot log in to the web UI. Available since 14.0. Keys are 20 random bytes and do not expire in 16 (live:
  `res_users.py` `API_KEY_SIZE`, no expiry field). A user with 2FA must use an API key, because the
  password alone no longer works over RPC.
- Odoo Online users have no password by default. An admin sets one, or the user creates an API key.
- `db.list` works only when the server runs with `list_db=True` (live: `service/db.py`). Production
  servers usually disable it. Ask the client for the DB name, or read it from the URL
  (`https://<db>.odoo.com`).
- Error shape (live):
  `{"error":{"code":200,"message":"Odoo Server Error","data":{"name":"odoo.exceptions.AccessError","message":"...","debug":"<traceback>"}}}`.
  Branch on `data.name`:
  - `AccessError`: rights.
  - `AccessDenied`: login.
  - `ValidationError` and `UserError`: a business rule.
  - `MissingError`: the record was deleted.
  - `builtins.ValueError` with "Invalid field": a wrong field name.

  The message is in the API user's language.

## 2. Hosting and plan

| Hosting | External API |
|---|---|
| Odoo Online | Only on the Custom plan. The 16.0 docs say: "Access to data via the external API is only available on Custom Odoo pricing plans." One App Free and Standard do not have it. |
| Odoo.sh | Yes (Custom plan). Custom modules are allowed. |
| On-premise Community or Enterprise | Yes. |

Rate limits: none documented (UNVERIFIED). Keep batches of about 50 to 200 records and use timeouts of
20 to 30 s.

## 3. Methods (ORM, 16.0 signatures)

| Method | Call (args, kwargs) | Notes |
|---|---|---|
| `search` | `[domain]`, `{offset, limit, order}` | Returns ids. |
| `search_count` | `[domain]` | |
| `read` | `[ids]`, `{fields}` | |
| `search_read` | `[domain]`, `{fields, offset, limit, order}` | Default limit is none, so always pass one. |
| `fields_get` | `[]`, `{attributes:[...]}` | Useful attributes are `string, type, required, readonly, relation, selection, store, help`. |
| `read_group` | `[domain, fields, groupby]`, `{offset, limit, orderby, lazy}` | Each row carries `<field>_count` (lazy). `orderby='x_count desc'` is invalid in 16 (live), so sort on the client. Date groupby takes `field:day/week/month/quarter/year`. |
| `create` | `[vals]` or `[[vals, ...]]` | Returns an id, or a list of ids. |
| `write` | `[ids, vals]` | Returns true. |
| `unlink` | `[ids]` | |
| `default_get` | `[field_names]` | Shows what Odoo fills on create. |
| `check_access_rights` | `[op]`, `{raise_exception: false}` | op is `read`, `write`, `create` or `unlink`. This checks ACLs only; record rules can still hide rows. |
| `name_search` | `[name]`, `{args: domain, limit}` | Fuzzy match on the display name. |

Workflow buttons are public methods called on ids. These were checked live in 16 source:

| Method | Effect |
|---|---|
| `purchase.order.button_confirm` | RFQ to PO |
| `sale.order.action_confirm` | Confirm the order |
| `account.move.action_post` | Post the move |
| `stock.picking.button_validate` | Validate the transfer; may return a wizard action when quantities are not set |

Methods starting with `_` cannot be called over RPC.

Domains: `[(field, op, value), ...]` with an implicit AND, and `'|'`, `'&'`, `'!'` as prefix operators.

- Operators: `= != > >= < <= =? like ilike not like not ilike =like =ilike in not in child_of parent_of`.
- Dotted paths work: `('partner_id.country_id.code','=','MA')`.
- Use `False` or `false` for empty values.

x2many Command tuples (send them as lists):

| Command | Effect |
|---|---|
| `[0,0,vals]` | create |
| `[1,id,vals]` | update |
| `[2,id,0]` | delete |
| `[3,id,0]` | unlink |
| `[4,id,0]` | link |
| `[5,0,0]` | clear |
| `[6,0,ids]` | set |

Context keys (pass as `kwargs.context`):

| Key | Effect |
|---|---|
| `lang` (`fr_FR`, `ar_001`) | Language of translated fields and messages |
| `tz` | Timezone |
| `active_test: false` | Include archived records |
| `allowed_company_ids: [ids]` | Multi-company. Without it, only the user's current company applies. |
| `tracking_disable: true` | Fewer chatter messages on bulk import |

## 4. Data conventions

- many2one reads come back as `[id, "Display Name"]` or `false`. Write the plain id.
- Unset values of any type come back as `false`, not `null`.
- Datetimes are UTC strings `YYYY-MM-DD HH:MM:SS`. Dates are `YYYY-MM-DD`. Convert to the user's tz on your side.
- Monetary fields are floats. Round to the currency's `decimal_places` before you write.
- `product.template` and `product.product`: the template carries the commercial data. Each variant is a
  `product.product`. Order lines, moves and invoice lines take a `product.product` id.
- `display_name` is readable on every model.

## 5. Models and fields (Odoo 16, all checked live)

| Model | Key fields | Selection values |
|---|---|---|
| `res.partner` | name, is_company, parent_id, type, vat, email, phone, mobile, ref, company_id, country_id, customer_rank, supplier_rank, category_id | type: contact, invoice, delivery, private, other |
| `product.template` / `product.product` | name, detailed_type, default_code, barcode, list_price, standard_price, uom_id, uom_po_id, categ_id, sale_ok, purchase_ok, taxes_id, supplier_taxes_id | detailed_type: consu, service, product (storable) |
| `sale.order` | name, partner_id, state, date_order, client_order_ref, origin, order_line, amount_total, invoice_status, pricelist_id | state: draft, sent, sale, done, cancel |
| `purchase.order` | name, partner_id, partner_ref, state, origin, date_order, date_planned, order_line, notes, invoice_status, picking_type_id | state: draft, sent, to approve, purchase, done, cancel (draft = RFQ) |
| `purchase.order.line` | product_id, name, product_qty, price_unit, product_uom, taxes_id, date_planned | |
| `account.move` | name, move_type, state, payment_state, partner_id, ref, invoice_date, invoice_date_due, journal_id, invoice_line_ids, amount_total, amount_residual, invoice_origin | move_type: entry, out_invoice, out_refund, in_invoice, in_refund, out_receipt, in_receipt; state: draft, posted, cancel; payment_state: not_paid, in_payment, paid, partial, reversed, invoicing_legacy |
| `account.move.line` | move_id, product_id, name, quantity, price_unit, tax_ids, account_id, display_type | display_type: product, cogs, tax, rounding, payment_term, line_section, line_note, epd |
| `account.payment` | payment_type, partner_type, partner_id, amount, journal_id, date, ref, state | payment_type: inbound, outbound |
| `stock.picking` | name, picking_type_id, state, origin, partner_id, scheduled_date, move_ids | state: draft, waiting, confirmed, assigned, done, cancel |
| `stock.quant` | product_id, location_id, quantity, reserved_quantity, lot_id | |
| `fleet.vehicle` | name, license_plate, vin_sn, driver_id, model_id (required), odometer, odometer_unit, fuel_type, state_id, company_id, active, acquisition_date | fuel_type: diesel, gasoline, ... |
| `fleet.vehicle.log.services` | vehicle_id (required), service_type_id (required), date, amount, vendor_id, description, odometer, state, purchaser_id, inv_ref, notes | state: new, running, done, cancelled |
| `fleet.service.type` | name, category | category: contract, service |
| `fleet.vehicle.odometer` | vehicle_id, value, date | |
| `hr.employee` | name, work_email, work_phone, job_id, department_id, user_id, parent_id, barcode, identification_id | |
| `crm.lead` | name, type, partner_id, email_from, phone, stage_id, user_id, expected_revenue, probability | type: lead, opportunity |

16 has no fuel log model (live: no `ir.model` matching "fuel"; fleet ships only `log.services` and
`log.contract`). Fuel goes in as a `fleet.vehicle.log.services` row with a service type named for fuel,
or into the client's custom model. Run `audit` to find out which.

Technical models for auditing:

| Model | What it holds | Readable by a non-admin? (live) |
|---|---|---|
| `ir.module.module` | modules, state, author | yes |
| `ir.model`, `ir.model.fields` | models and fields; `state='manual'` marks custom `x_` ones | no |
| `ir.model.data` | external ids `module.name` mapped to `res_id` | |
| `ir.cron` | scheduled jobs (`nextcall` in the past = stuck) | no |
| `base.automation` | automated actions (module `base_automation`) | |
| `ir.actions.server` | server actions | |
| `ir.config_parameter` | `web.base.url` and settings | no |
| `ir.mail_server`, `fetchmail.server`, `mail.mail` | mail (`state='exception'` on `mail.mail` = failed sends) | |
| `res.users.apikeys` | API keys | admin only |

## 6. Security model

- ACLs (`ir.model.access`) are per group and per model, and set read, write, create and unlink.
  `check_access_rights` tests these.
- Record rules (`ir.rule`) filter rows by domain. A user can have read on a model and still see zero rows.
  Live example: a Fleet / User sees only their own vehicles, so `fleet.vehicle` count was 0 for a
  Fleet-User API account while the admin saw 5. Always compare a limited user's counts with an admin's
  before you trust them.
- Multi-company: rows are filtered by `allowed_company_ids`. Set `company_id` explicitly on create when
  the client has several companies.
- Integration user: an internal user (not portal), with only the groups the app needs. One user per
  integration, so its writes are traceable in the chatter (`create_uid` / `write_uid`). Not an admin.

## 7. Idempotency (no duplicates)

Search for the key, then create. Repeat the search before every retry. Where the key lives:

1. A custom indexed char field `x_ext_key`. The client admin adds it, or Studio does.
2. A standard reference field:
   - `origin` on purchase.order, sale.order and stock.picking;
   - `ref` on account.move and res.partner;
   - `partner_ref` on purchase.order;
   - `client_order_ref` on sale.order;
   - `default_code` on products.
3. An external id in `ir.model.data` (`module='__myapp__'`). The API user needs rights on ir.model.data.

See `laravel.md` for the full pattern and the "created, answer lost" test.

## 8. Pull and push

- Pull incrementally on `write_date > last_seen`, ordered `write_date asc, id asc`, paged. Archived rows
  need `active_test: false`. Deletions need a periodic id diff.
- Push from Odoo 16: there is no webhook action. That was added to Automation Rules in 17. Server-action
  Python cannot make HTTP calls; it has no `requests` and no imports (live: `ir_actions.py` eval context).
  So use polling, or a custom module on self-hosted or Odoo.sh.

## 9. After 16

- 17: Automation Rules gain "Send Webhook Notification"
  ([17.0 docs](https://www.odoo.com/documentation/17.0/applications/studio/automated_actions.html)). Several UI and field renames.
- 17 and 18: `fields_view_get` is gone; use `get_views`. Some field renames, for example `detailed_type`
  becomes `type` with new values in 18 (UNVERIFIED in detail). Always `fields_get` before mapping.
- 19: a new JSON-2 API at `/json/2/<model>/<method>`, with bearer API-key auth and named arguments.
  `/xmlrpc` and `/jsonrpc` are deprecated. The removal version is UNVERIFIED and sources conflict: the 19
  docs said 20.0, later reports say it was postponed to 21.1 for Online and 22.0 for on-premise. The
  `audit` flags any server at 19 or later. Keep the transport behind one class so the move is a single
  change.
