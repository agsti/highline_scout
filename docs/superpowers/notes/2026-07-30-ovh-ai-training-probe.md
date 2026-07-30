# OVH AI Training probe

Measured on 2026-07-30 UTC with `ovhai 3.37.0`.

## Container resources

Probe job:

```text
ovhai job run --cpu 4 --name probe-1 ubuntu:24.04 -- \
  bash -c 'id; echo ---; df -h /; echo ---; nproc; free -g; echo ---; touch /artifacts/x 2>&1 || echo "/artifacts not writable"'
```

Job id: `e766b442-7db0-44e2-9f66-5cd51cfa9d14`

The job printed:

```text
uid=42420(ovh) gid=42420(ovh) groups=42420(ovh)
Filesystem      Size  Used Avail Use% Mounted on
overlay         387G  207G  181G  54% /
4
Mem:              61           3           2           0          55          57
Swap:              0           0           0
touch: cannot touch '/artifacts/x': No such file or directory
/artifacts not writable
```

The machine-readable resource allocation was 160 GiB ephemeral storage
(`171798691840` bytes) and 16 GiB memory (`17179869184` bytes) at four CPUs.
The larger values printed by `df` and `free` are the container-visible host
values, not the allocation.

The runner stage must not set `USER`: AI Training imposes uid/gid `42420`, and
leaving the image as root lets the platform select that user. The image's
`/app` working directory must be mode `0777` so that imposed user can create
repo-relative `data/`, `cache/`, and other outputs. `/artifacts` does not exist
unless a volume is attached.

## Object Storage volume

Created the `highline-runs` container in the `GRA` datastore, then ran:

```text
ovhai job run --cpu 1 --name probe-2 \
  --volume highline-runs@GRA:/artifacts:rw \
  ubuntu:24.04 -- bash -c 'touch /artifacts/hello && ls -la /artifacts'
```

Job id: `71c98d04-2956-4566-89b5-c4ea9f20b009`

The exact accepted syntax is:

```text
--volume <container>@<datastore-alias>:/artifacts:rw
```

The write succeeded as uid/gid `42420`; `hello` was subsequently visible via
`ovhai bucket object list highline-runs@GRA`.

## Machine-readable job interface

`ovhai job run --output json` and `ovhai job get <id> --output json` use:

- job id: `.id`
- state: `.status.state`
- process exit code: `.status.exitCode`

Observed lifecycle states were `QUEUED`, `INITIALIZING`, `PENDING`, `RUNNING`,
`FINALIZING`, and terminal state `DONE`. The CLI's documented other terminal
states are `TIMEOUT`, `FAILED`, `ERROR`, `INTERRUPTED`, and `SYNC_FAILED`.

## Billing

Not verified. The `ovhai` CLI does not expose the billing source, and no
OVHcloud Manager API credentials are configured in this workspace. Before
submitting a non-probe workload, confirm in the OVHcloud control panel that
these two probe jobs were charged against trial credits rather than a payment
method.
