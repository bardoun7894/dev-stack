# system-design reviewer checklist

Run before the hard stop. One line per check.

- [ ] First line states LITE or FULL and why.
- [ ] Every number in section 1 is real or points to a Q-code; none invented.
- [ ] Each part has a named host; Syrian-user projects are on Hetzner, not Contabo.
- [ ] Reuse inventory done: Temporal, pm2/Docker, Laravel/Next.js, Kie.ai, OpenRouter, Jev considered before new infra.
- [ ] Every new service, datastore, queue, provider or host has a D-code saying why reuse failed.
- [ ] Container diagram shows every component named elsewhere in the file.
- [ ] Capacity section shows arithmetic and a cost per unit for AI/media calls.
- [ ] Each entity has one owning component, a retention period and a backup.
- [ ] Critical paths show timeouts, retries and idempotency keys on every external call.
- [ ] Failure table covers each external provider and each datastore; SPOFs listed; restore test named.
- [ ] Secrets location, tenant isolation, PII handling and rate limits stated.
- [ ] Deploy script path, health check, rollback and Telegram/Tokyo alert present.
- [ ] Each D-code has options, choice, why and reversible yes/no.
- [ ] Load-bearing D-codes carry the one fusion /opinion verdict.
- [ ] No product/UX design, no library list, no field-level schema (those live elsewhere).
- [ ] Q-codes are answerable by the owner in one line each.
- [ ] `scripts/check.sh` exits 0.
