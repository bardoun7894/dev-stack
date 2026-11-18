# Connecting a Laravel app to Odoo (JSON-RPC)

For the owner's Laravel 12 apps (jaafar-odoo, AMIIN INOX, station ERP style). No package needed: one
`OdooGateway` contract, one HTTP implementation, one fake for tests. The contract names match
`jaafar-odoo/specs/001-odoo-intake/system-design.md` section 4 (`authenticate`, `searchRead`,
`fieldsGet`, `create`); reuse it, do not invent a second one. Copy the code per client repo; never share
it across clients.

## Settings

Store per tenant in `settings` (or `.env` for a single tenant): `odoo.url`, `odoo.db`, `odoo.login`,
`odoo.api_key`. Encrypt the key (`Crypt::encryptString`), write-only in the UI, never logged, never sent to
an AI prompt. Use a dedicated Odoo internal user with only the groups the app needs.

## Contract

```php
namespace App\Contracts;

interface OdooGateway
{
    public function authenticate(): int;                                    // uid
    public function version(): array;                                       // no login
    public function searchRead(string $model, array $domain = [], array $fields = [],
                               int $limit = 80, int $offset = 0, ?string $order = null): array;
    public function searchCount(string $model, array $domain = []): int;
    public function fieldsGet(string $model, array $attributes = ['string','type','required','relation','selection']): array;
    public function create(string $model, array $values): int;
    public function write(string $model, array $ids, array $values): bool;
    public function call(string $model, string $method, array $args = [], array $kwargs = []): mixed;
}
```

## HTTP implementation

```php
namespace App\Services\Odoo;

use App\Contracts\OdooGateway;
use Illuminate\Support\Facades\Http;
use RuntimeException;

class OdooException extends RuntimeException
{
    public function __construct(public string $odooName, string $message)
    {
        parent::__construct("$odooName: $message");
    }
    public function isAccess(): bool { return str_ends_with($this->odooName, 'AccessError'); }
    public function isValidation(): bool { return str_ends_with($this->odooName, 'ValidationError')
        || str_ends_with($this->odooName, 'UserError'); }
}

class JsonRpcOdoo implements OdooGateway
{
    private ?int $uid = null;
    private int $id = 0;

    public function __construct(
        private string $url, private string $db, private string $login, private string $key,
        private array $context = [], private int $timeout = 20,
    ) {}

    private function rpc(string $service, string $method, array $args): mixed
    {
        $res = Http::timeout($this->timeout)->acceptJson()
            ->post(rtrim($this->url, '/').'/jsonrpc', [
                'jsonrpc' => '2.0', 'method' => 'call', 'id' => ++$this->id,
                'params' => ['service' => $service, 'method' => $method, 'args' => $args],
            ])->throw()->json();
        if (isset($res['error'])) {
            $d = $res['error']['data'] ?? [];
            throw new OdooException($d['name'] ?? 'OdooError', $d['message'] ?? $res['error']['message']);
        }
        return $res['result'] ?? null;
    }

    public function version(): array { return $this->rpc('common', 'version', []); }

    public function authenticate(): int
    {
        if ($this->uid === null) {
            $uid = $this->rpc('common', 'authenticate', [$this->db, $this->login, $this->key, []]);
            if (! $uid) {
                throw new OdooException('AccessDenied', 'Odoo login failed (db, login, API key, or plan without API)');
            }
            $this->uid = $uid;
        }
        return $this->uid;
    }

    public function call(string $model, string $method, array $args = [], array $kwargs = []): mixed
    {
        if ($this->context) {
            $kwargs['context'] = array_merge($this->context, $kwargs['context'] ?? []);
        }
        return $this->rpc('object', 'execute_kw',
            [$this->db, $this->authenticate(), $this->key, $model, $method, $args, (object) $kwargs]);
    }

    public function searchRead(string $model, array $domain = [], array $fields = [],
                               int $limit = 80, int $offset = 0, ?string $order = null): array
    {
        $kw = ['fields' => $fields, 'limit' => $limit, 'offset' => $offset];
        if ($order) { $kw['order'] = $order; }
        return $this->call($model, 'search_read', [$domain], $kw);
    }

    public function searchCount(string $model, array $domain = []): int
    {
        return $this->call($model, 'search_count', [$domain]);
    }

    public function fieldsGet(string $model, array $attributes = ['string','type','required','relation','selection']): array
    {
        return $this->call($model, 'fields_get', [], ['attributes' => $attributes]);
    }

    public function create(string $model, array $values): int
    {
        return $this->call($model, 'create', [$values]);
    }

    public function write(string $model, array $ids, array $values): bool
    {
        return $this->call($model, 'write', [$ids, $values]);
    }
}
```

Bind it in `AppServiceProvider`, building it from settings; tests bind the fake.

PHP gotchas:
- `(object) $kwargs` so an empty kwargs is sent as `{}`, not `[]`.
- An empty `$values` array must also go as `(object) []` if you ever send one.
- Domains are arrays of arrays: `[['license_plate', '=', 'A-12345'], ['active', '=', true]]`; `'|'` and
  `'&'` are plain strings in the list.
- many2one comes back as `[id, "Name"]` or `false`. Unset fields are `false`, not `null`.
- Datetimes are UTC strings `Y-m-d H:i:s`; dates `Y-m-d`. Convert with `Carbon::parse($v, 'UTC')`.
- Money: Odoo floats. Keep decimal strings on your side; send `(float)` only at the boundary and round to
  the currency precision first.

## Exactly-once write (the duplicate killer)

```php
public function writeOnce(string $model, string $keyField, string $key, array $values): int
{
    // 1. our table: odoo_writes(intake_key UNIQUE, model, odoo_id, request, response, attempts)
    if ($done = OdooWrite::where('intake_key', $key)->whereNotNull('odoo_id')->first()) {
        return $done->odoo_id;
    }
    // 2. Odoo itself: a create that succeeded but whose answer was lost is found here
    $found = $this->odoo->searchRead($model, [[$keyField, '=', $key]], ['id'], 1);
    $id = $found[0]['id'] ?? $this->odoo->create($model, $values + [$keyField => $key]);
    OdooWrite::updateOrCreate(['intake_key' => $key], ['model' => $model, 'odoo_id' => $id]);
    return $id;
}
```

Key field choice, best first:
1. A custom char field `x_ext_key` (or `x_intake_key`), added by the client's admin in Settings >
   Technical > Fields or by Studio, indexed. Exact match, invisible to users.
2. A standard reference field the model already has: `origin` (purchase.order, sale.order,
   stock.picking), `ref` (account.move, res.partner), `client_order_ref` (sale.order), `partner_ref`
   (purchase.order), `default_code` (product.product).
3. External IDs: create the record, then create `ir.model.data` with
   `{module: '__myapp__', name: 'intake_<key>', model, res_id}`; look it up with
   `searchRead('ir.model.data', [['module','=','__myapp__'],['name','=','intake_<key>']], ['res_id'])`.
   Needs create rights on ir.model.data, which a limited user usually does not have.

Retries run in a queued job (3 tries, 10 s / 60 s / 5 min) and each retry starts at step 2.

## x2many writes

Lines are created inside the parent with command tuples, as arrays:

```php
$this->odoo->create('purchase.order', [
    'partner_id' => $vendorId,
    'origin'     => $key,
    'order_line' => [
        [0, 0, ['product_id' => $pid, 'product_qty' => 200, 'price_unit' => 12.5, 'name' => 'Gasoil']],
    ],
]);
// many2many: replace all tags
$this->odoo->write('res.partner', [$partnerId], ['category_id' => [[6, 0, [3, 7]]]]);
```

Codes: 0 create, 1 update(id, vals), 2 delete(id), 3 unlink(id), 4 link(id), 5 clear, 6 set(ids).

## Fake for tests

```php
class FakeOdoo implements OdooGateway
{
    public array $records = [];   // [model => [id => values]]
    public array $calls = [];
    public ?\Throwable $failNextCreate = null;
    private int $next = 100;

    public function authenticate(): int { return 2; }
    public function version(): array { return ['server_version' => '16.0', 'server_serie' => '16.0']; }
    public function searchRead(string $model, array $domain = [], array $fields = [], int $limit = 80, int $offset = 0, ?string $order = null): array
    {
        $this->calls[] = ['searchRead', $model, $domain];
        $rows = [];
        foreach ($this->records[$model] ?? [] as $id => $v) {
            $ok = true;
            foreach ($domain as $c) {
                if (is_array($c) && $c[1] === '=' && ($v[$c[0]] ?? null) !== $c[2]) { $ok = false; }
            }
            if ($ok) { $rows[] = ['id' => $id] + $v; }
        }
        return array_slice($rows, $offset, $limit);
    }
    public function searchCount(string $model, array $domain = []): int { return count($this->searchRead($model, $domain, [], PHP_INT_MAX)); }
    public function fieldsGet(string $model, array $attributes = []): array { return []; }
    public function create(string $model, array $values): int
    {
        $this->calls[] = ['create', $model, $values];
        $id = $this->next++;
        $this->records[$model][$id] = $values;
        if ($e = $this->failNextCreate) { $this->failNextCreate = null; throw $e; } // created, answer lost
        return $id;
    }
    public function write(string $model, array $ids, array $values): bool { return true; }
    public function call(string $model, string $method, array $args = [], array $kwargs = []): mixed { return null; }
}
```

The `failNextCreate` case is the test that matters: create succeeds in Odoo, the answer is lost, the retry
must find the record by key and not create a second one.

## Pulling data (sync into the app)

- Incremental: keep the last `write_date` you saw per model, then
  `searchRead($model, [['write_date', '>', $last]], $fields, 500, 0, 'write_date asc, id asc')`, page until
  empty. Deleted records do not show; run a weekly full id diff (`search` with `active_test: false` in context).
- Cache small lists (vehicles, partners, products, taxes, journals) in local tables, refreshed hourly, to
  match AI-extracted text locally instead of calling Odoo per message.

## Odoo pushing to the app (outbound)

Odoo 16 has no "Send webhook" action (Automation Rules got it in 17). A Python code server action cannot
make HTTP calls either: its eval context (16.0 `ir_actions.py` `_get_eval_context`) offers `env`, `model`,
`record(s)`, `time`, `datetime`, `dateutil`, `timezone`, `float_compare`, `b64encode/decode`, `Command`,
`log`, and no `requests`; `import` is blocked by safe_eval. So in 16, outbound push needs a small custom
module (self-hosted or Odoo.sh only). Default: poll by `write_date` every few minutes.
