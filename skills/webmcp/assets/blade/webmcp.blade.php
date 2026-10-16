{{-- WebMCP tools partial. Usage: @push('scripts') @include('partials.webmcp', ['tools' => [...]]) @endpush
     $tools: list of ['name','description','inputSchema','annotations'?,'method'?,'url'] ;
     execute() calls the existing same-origin route, with {name} placeholders filled from input. --}}
<script>
(function () {
  var mc = document.modelContext;
  if (!mc || typeof mc.registerTool !== 'function') return;
  var csrf = document.querySelector('meta[name="csrf-token"]');
  var token = csrf ? csrf.getAttribute('content') : '{{ csrf_token() }}';
  var ac = new AbortController();
  var tools = @json($tools);

  tools.forEach(function (t) {
    // Chrome 156: the returned promise rejects with AbortError on unregister.
    Promise.resolve(mc.registerTool({
      name: t.name,
      description: t.description,
      inputSchema: t.inputSchema,
      annotations: t.annotations || {},
      execute: async function (input, ctx) {
        var method = (t.method || 'GET').toUpperCase();
        var url = t.url.replace(/\{(\w+)\}/g, function (_, k) { return encodeURIComponent(input[k]); });
        var opts = { method: method, credentials: 'same-origin', signal: ctx && ctx.signal,
                     headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' } };
        if (method === 'GET') {
          url += (url.indexOf('?') < 0 ? '?' : '&') + new URLSearchParams(input).toString();
        } else {
          opts.headers['Content-Type'] = 'application/json';
          opts.headers['X-CSRF-TOKEN'] = token;
          opts.body = JSON.stringify(input);
        }
        var res = await fetch(url, opts);
        return { content: [{ type: 'text', text: await res.text() }], isError: !res.ok };
      }
    }, { signal: ac.signal })).catch(function (err) {
      if (!ac.signal.aborted) console.warn('WebMCP: ' + t.name + ' was rejected', err);
    });
  });

  window.addEventListener('pagehide', function () { ac.abort(); });
})();
</script>
