# `cad_bridge/` - the CAD half of the contract, kept out of the CAD skill

`parametric-3d-printing` is a third-party skill under the PolyForm Noncommercial
licence. Patching it in place would work until the next upgrade quietly
overwrote the patch, so the bridge lives here instead. **Nothing in this folder
modifies that skill, and nothing here imports CadQuery.**

## Two problems it solves

### 1. The manifest has to reach the CAD script as data

A CadQuery script that types `spk_d = 20.0` into itself has broken the contract
before it runs: the hash lock cannot invalidate a number it cannot see.
`consume_manifest.py params` flattens the manifest into a parameter dict and an
importable `manifest_params.py`, so the script *reads* every electronics-owned
number instead of restating it.

### 2. CadQuery's exit code is unreliable on this platform

CadQuery scripts here routinely exit **-1073740940** (heap corruption) or
**-1073741819** (access violation) **on success** — OpenCASCADE crashes during
interpreter teardown, after the STL is already on disk.

The CAD skill's own wrapper does:

```python
result["success"] = proc.returncode == 0
if result["success"]:
    ...discover the STL files...
```

so under that crash **every successful build reports failure with an empty
`stls` list**. `run_cad_model.py` judges the run by a stdout sentinel and by
freshly written artefacts, and never by `returncode`.

## Workflow

```powershell
$py = "..\.venv\Scripts\python.exe"
$m  = "..\examples\pager-style-handheld\component-manifest.json"

# 1. Manifest -> parameters the CAD script imports
& $py cad_bridge\consume_manifest.py params $m `
      --out cad-params.json --out-py manifest_params.py

# 2. The keep-out and containment budget, as data
& $py cad_bridge\consume_manifest.py envelope $m

# 3. Run the CadQuery script without trusting its exit code
& $py cad_bridge\run_cad_model.py pager_enclosure.py --expect-stl pager_p2_back_shell.stl

# 4. Scaffold the reply, fill it in, pre-flight it
& $py cad_bridge\consume_manifest.py respond $m --out cad-response.json
& $py cad_bridge\consume_manifest.py check   $m --response cad-response.json

# 5. Hand it back to the electronics side for the substantive checks
& $py handoff_lint.py $m --check-response cad-response.json --check-lock cad_lock.json --strict
```

## Using it from the CAD skill without changing that skill

Tell the agent, in the project (not in the vendored skill):

> Before generating geometry, run
> `devboard-electronics/cad_bridge/consume_manifest.py params <manifest> --out-py manifest_params.py`
> and `import manifest_params` in the CadQuery script. Do not type any dimension
> that appears in `manifest_params.PARAMS` directly into the script. Run the
> script through `cad_bridge/run_cad_model.py`, not through
> `run_cadquery_model.py`, because the latter treats an OpenCASCADE teardown
> crash as a build failure. When the geometry is exported, run
> `consume_manifest.py respond` and fill in every assertion.

That is the whole integration. It is a project instruction, not a fork.

## Add the sentinel to your CAD script

One line, at the end:

```python
import json
print("HWEL_RESULT " + json.dumps({"ok": True, "stls": ["front.stl", "back.stl"]}))
```

A missing sentinel falls back to timestamp-based artefact detection and produces
a `NO_SENTINEL` warning. A nonzero exit **with** a valid sentinel is a pass.

## What the bridge will not do for you

- It will not invent a placement. Placement is CAD-owned and absent from
  `params` on purpose.
- It will not add clearance. Electronics states a dimension and its tolerance;
  CAD owns print clearance. Adding your own on top is double-clearancing, and it
  is invisible until the part rattles.
- It will not rotate a part whose `orientation_constraint.locked` is true.
  `consume_manifest.py check` reports `ORIENTATION_VIOLATED` if a response tries.
- It will not let a scaffolded `not_evaluated` assertion through. Silence is not
  a pass.
- It will not quietly shrink a cable channel below its declared minimum. That
  failure is the quiet one: the model just fits the channel around whatever else
  is in the way, and nothing tells you the cable will not go in.
