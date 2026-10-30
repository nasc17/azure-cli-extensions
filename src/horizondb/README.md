# Azure CLI HorizonDB Extension

This extension manages Azure HorizonDB using AAZ REST operations for API
`2026-10-01-preview`. It does not depend on the HorizonDB management SDK.

## How to use

Install this extension using the following CLI command:

```bash
az extension add --name horizondb
```

## Local development

From the repository root, activate your development virtual environment and
install this extension from source:

```powershell
.\venv\Scripts\Activate.ps1
python -m pip install azdev
azdev setup -r "$PWD" -e horizondb
```

Confirm that the extension path points to this checkout and try the generated
pool command group:

```powershell
az extension show --name horizondb
az horizondb cluster pool --help
```

Local source edits take effect on the next command invocation. The generated
pool commands are under `horizondb cluster pool`, not `horizondb pool`.

## Create a cluster resource

`az horizondb cluster create` invokes only the Create Cluster API. It does not
create a pool, configure authentication, or create firewall rules, and it accepts
no pool compute or availability arguments. It supports `--no-wait` for the
cluster's long-running operation. `--postgresql-version` is required and the creation mode
is fixed to `Create`; `--creation-mode` and restore source/time options are not exposed:

```powershell
az horizondb cluster create --resource-group example-resource-group --name example-cluster --location eastus2 --postgresql-version 17 --geo-redundancy Enabled
```

Create a pool separately with `az horizondb cluster pool create`, or use
`az horizondb create` for the full setup workflow described below.
Omitted backup settings are left out of the request so the service applies its
defaults, including seven-day retention. If supplying `--backup-retention-days`, also
supply `--geo-redundancy` as required by the backup API object.

## Command coverage and hierarchy

The extension uses the nested AAZ hierarchy. The provider Operations API is
intentionally not exposed. The `cluster log-capture-configuration` and
`cluster log-file` groups are withheld until their backend APIs are implemented
(currently HTTP 501). They are not registered or callable. Private endpoint connection
state changes use only `approve` and `reject`; the redundant `create` and `update`
alternatives are not exposed. The extension retains firewall-rule `update` and a
separate `cluster restore` command, for 83 public commands in total.

The authored command loader removes unsupported log registrations from existing
generated assets. `dev/generate.py` also excludes those resource paths, so future
generation does not restore them. Generated operation files are left untouched.
The loader also removes private-endpoint-connection `create`/`update` registrations.
Generation clones `approve`/`reject` first, then removes only the `create`/`update`
leaves, preserving `show`, `list`, `delete`, and `wait`.

All command groups below are prefixed with `az horizondb`:

| Group | Commands |
| --- | --- |
| (root) | `create` |
| `cluster` | `create`, `restore`, `show`, `list`, `update`, `delete`, `failover`, `wait` |
| `cluster pool` | `create`, `show`, `list`, `update`, `delete`, `start`, `stop`, `restart`, `wait` |
| `cluster pool node` | `show`, `list` |
| `cluster pool firewall-rule` | `create`, `show`, `list`, `update`, `delete`, `wait` |
| `cluster endpoint` | `show`, `list` |
| `cluster authentication` | `list` |
| `cluster authentication password` | `create`, `show`, `update`, `wait` |
| `cluster authentication microsoft-entra` | `create`, `show`, `update`, `wait` |
| `cluster microsoft-entra-administrator` | `create`, `show`, `list`, `delete`, `wait` |
| `cluster change-data-capture` | `create`, `show`, `list`, `update`, `delete`, `wait` |
| `cluster change-data-capture-destination` | `create`, `show`, `list`, `update`, `activate-identity`, `delete`, `wait` |
| `cluster change-data-capture-destination identity-assignment` | `create`, `show`, `list`, `delete`, `wait` |
| `cluster change-data-capture-configuration` | `create`, `show`, `list`, `update`, `delete`, `wait` |
| `cluster private-endpoint-connection` | `show`, `list`, `approve`, `reject`, `delete`, `wait` |
| `cluster private-link-resource` | `show`, `list` |
| `parameter-group` | `create`, `show`, `list`, `update`, `delete`, `wait` |
| `parameter-group connection` | `list` |
| `default-parameter-group` | `show`, `list` |

For example, the former `horizondb pool start` becomes
`horizondb cluster pool start`; the former
`horizondb change-data-capture-identity-assignment list` becomes
`horizondb cluster change-data-capture-destination identity-assignment list`.
Cluster and parameter-group `list` commands support subscription and
resource-group scopes.

Regional capabilities are generated for internal discovery but have no public
commands or help groups. The provider Operations API and maintenance events are
also excluded from the customer-facing command surface.

## Help, examples, and argument names

All 83 public commands include examples in their command help (107 examples in total).
Resource commands use AAZ help, while the root convenience command uses standard Azure
CLI help. Examples are adapted to the nested hierarchy. Examples for withheld log
commands, redundant private endpoint connection verbs, and provider Operations are omitted.
Cluster restore examples belong to `cluster restore`, not `cluster create`.

Matching arguments use the original SDK-based command spellings, configured
directly in AAZ generation. For example, use `--postgresql-version`,
`--backup-retention-days`, `--compute-generation`, and `--high-availability-mode`.
Redesign-only spellings are not retained as compatibility aliases. Original
selectors such as `--resource-group`/`-g` and `--name`/`-n` remain available where
applicable; parent resources use `--cluster-name`, `--pool-name`, or
`--destination-name`. Use `az horizondb <command> --help` for accepted options.
AAZ structured encryption, identity helpers, and Fabric destination inputs
retain their native syntax rather than introducing differently shaped flat options.

Commands have short summaries and longer descriptions. Generated resource
arguments also have short and long help; root convenience arguments use standard
Azure CLI argument help.
Command short summaries describe the action concisely; detailed API behavior
belongs in the long description.
Examples are independent, not a deployment script. They use non-sensitive fake
names and resource IDs rather than environment variables. All sample GUIDs,
including subscription, tenant, principal, and workspace IDs, are zero initialized
(`00000000-0000-0000-0000-000000000000`). Passwords are redacted
as `"***"`, not shown as real or fake values. Replace the sample values as needed
and use secure input for real credentials. Do not use `--debug` when supplying them.
AAZ structured properties use shorthand objects and lists, for example:

```powershell
az horizondb parameter-group create -g example-rg -n pg-transactional -l eastus2 --postgresql-version 17 --parameters "[{name:shared_buffers,value:2048MB},{name:work_mem,value:64MB}]"
az horizondb cluster change-data-capture-destination create -g example-rg --cluster-name example-cluster -n fabric-main --desired-state Enabled --destination "{fabric:{workspace-id:00000000-0000-0000-0000-000000000000},protocol:Native}"
```

Pool creation can select an explicit location default parameter group using
`--parameter-group` and `--parameter-apply-method` together.
Omit both to let the service select its default. Cluster update supports
`--remove-user-assigned-identities` for removing unreferenced identities with
explicit null PATCH entries; other identity assignments are preserved.

## Convenience creation and restore

`az horizondb create` is the create-only convenience workflow. It discovers
regional defaults, creates a cluster and pool, configures authentication, and
adds public-access firewall rules, and configures data encryption, managed
identities, backup settings, and AI model management. It retains the original
convenience command's configuration options, including explicit pool sizing,
Entra/Password/Both authentication, and restore settings. Unlike `cluster create`,
it is responsible for discovery and setup. Its pool name defaults to the first
58 cluster-name characters followed by `-pool`, or can be set with `--pool-name`.
The workflow is a standard custom command registered in `commands.py`, with
arguments in `_params.py` and generated examples and command help in `_help.py`.
Its Python orchestration uses generated AAZ commands directly; it does not invoke
another Azure CLI process or require a HorizonDB management SDK. The root command
does not maintain its own AAZ class or argument schema. Resources are retained if
a later setup step fails.

`az horizondb cluster restore` uses the same Cluster PUT API with creation mode
fixed to `PointInTimeRestore`. It requires `--creation-source-cluster`
and `--point-in-time`, and also accepts `--creation-source-cluster-location`.
It exposes neither `--creation-mode` nor `--postgresql-version`: the service obtains the
PostgreSQL version from backup metadata.
The source location is required for cross-location restore. The API requires a
timestamp for cross-location restore but restores the latest available backup.
Restore does not clone source pools or firewall rules. `az horizondb create`
retains `--creation-mode PointInTimeRestore` for the full convenience workflow
and provisions and configures a new pool; `az horizondb cluster restore` restores
only the cluster resource.

```powershell
az horizondb cluster restore -g example-rg -n restored-cluster -l eastus2 --creation-source-cluster "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example-rg/providers/Microsoft.HorizonDb/clusters/source-cluster" --point-in-time 2026-10-01T12:00:00Z
```

Single-resource long-running commands expose `--no-wait`, with corresponding
`wait` commands for resource provisioning. The multi-step `az horizondb create` workflow
waits for dependent resources rather than returning after only the first PUT.

## Regenerating the AAZ commands

The API reference is [Azure/azure-rest-api-specs#47650](https://github.com/Azure/azure-rest-api-specs/pull/47650),
commit `8c2fc310736bbc98bfa2f387bbf118ee48600314`. The input is
`specification/horizondb/resource-manager/Microsoft.HorizonDb/HorizonDb/preview/2026-10-01-preview/openapi.json`
in that repository (SHA-256
`5e81d7770d1b0e43c62776942603461724794f61486bf89149ee1587fbed036e`).

Use a separate tooling environment with `aaz-dev==4.7.2`, a full
[AAZ definitions](https://github.com/Azure/aaz) checkout, and the API checkout
above. From this repository's root:

```powershell
python -m pip install aaz-dev==4.7.2
python src\horizondb\dev\generate.py --specs C:\source\azure-rest-api-specs --aaz C:\source\aaz
```

The generator script imports the updated Swagger, applies the nested naming and
argument customizations, exports the models into the AAZ checkout, and generates
the extension's Python files. It generates separate cluster create/restore
commands with constant creation modes and mode-specific arguments, plus fixed-status private endpoint
approval/rejection operations. The AAZ checkout is modified by this operation.
Regeneration alone from older AAZ definitions does **not** import API changes.
Do not manually edit generated files.

Custom creation orchestration lives outside the generated tree, so regeneration
does not delete it. The generator also runs `dev/command_help.py`, which emits
examples directly into generated command docstrings (consumed as `AZ_HELP` by
AAZ) and the custom commands' own help declarations. There is no runtime example
registry. Edit the example inputs in that helper rather than generated files.
For help-only changes, regenerate without the API/AAZ tooling dependencies:

```powershell
python src\horizondb\dev\command_help.py
```

Run the offline regression suite after regenerating. It checks all examples
against the CLI parser and AAZ schemas, canonical per-command examples,
argument-guided help loading, and idempotent help generation:

```powershell
$env:PYTHONPATH = Join-Path $PWD 'src\horizondb'
python -m pytest src\horizondb\azext_horizondb\tests\latest -q
```
