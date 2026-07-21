# Hetzner CPX22 provisioning script

## Purpose

A one-off utility script to spin up N disposable Hetzner Cloud CPX22 servers,
each bootstrapped with the tools needed to run this repo's ETL/agent tooling
(`git`, `uv`, `pi`, `awscli`) plus an arbitrary set of local files (secrets,
scripts, configs) the operator wants present on every box. This is purely a
provisioning tool — it does not decide what work each server does after boot.

## Interface

```
scripts/create_hetzner_servers.sh <N> <bootstrap-dir>
```

- `N` — number of CPX22 servers to create.
- `bootstrap-dir` — local directory. Every regular file directly inside it is
  embedded into the generated cloud-init user-data and written to
  `/root/bootstrap/<basename>` on each server, preserving the source file's
  executable bit.

## Hardcoded server config

No CLI flags for these; edit the script to change them.

- Server type: `cpx22`
- Image: `ubuntu-24.04`
- Datacenter: `nbg1`
- SSH key: `hetzner` (must already exist in the Hetzner project — the script
  does not create it)
- Names: `cpx22-1` … `cpx22-N`

## Prerequisites (checked, never auto-installed)

The script requires the `hcloud` CLI on the operator's machine, already
authenticated (existing context or `HCLOUD_TOKEN`). If `hcloud` is not on
`PATH`, the script prints an install pointer and exits non-zero before
creating anything. The script never installs or modifies anything on the
operator's own machine.

## Cloud-init bootstrap

For each run, the script generates a single cloud-config YAML (identical
across all N servers, since they share one `bootstrap-dir`) with:

- `packages`: `git`, `curl`, `nodejs`, `npm`, `awscli` (installed via apt)
- `runcmd`:
  - install `uv` via the official astral.sh installer
    (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
  - `npm install -g @earendil-works/pi-coding-agent` (provides the `pi` CLI
    used by `scripts/agent_etl.sh`)
- `write_files`: one entry per file in `bootstrap-dir`, base64-encoded,
  written to `/root/bootstrap/<basename>` with the source file's permission
  bits preserved

## Creation flow

1. Validate args: `N` is a positive integer, `bootstrap-dir` exists and is a
   directory.
2. Check `hcloud` is on `PATH`; exit with an install pointer if not.
3. Generate the cloud-init YAML once (embedding every file in
   `bootstrap-dir`), write it to a temp file.
4. Loop `i` from 1 to `N`:
   - Run `hcloud server create --type cpx22 --image ubuntu-24.04
     --datacenter nbg1 --ssh-key hetzner --name cpx22-$i
     --user-data-from-file <tmpfile>`.
   - Print the server's name and IP on success.
   - On failure, print the error and continue to the next `i` rather than
     aborting the whole batch — a single `hcloud` failure (e.g. a name
     collision from a previous run) shouldn't stop the rest of the servers
     from being created.
5. Clean up the temp cloud-init file.

## Out of scope

- No teardown/delete script.
- No per-server task assignment (e.g. GitHub issue numbers) — bootstrapping
  and dispatching work to a server are separate concerns.
- No flags to override type/image/datacenter/ssh-key — hardcoded per above;
  trivial to add later if needed.
