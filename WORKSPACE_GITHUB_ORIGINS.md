# Workspace Git `origin` URLs

Generated to verify each local clone points at the expected GitHub organization.

| Local path | `origin` (fetch) | Noma-Travel? |
|------------|------------------|--------------|
| `C:/Noma/NOMA` | `https://github.com/Noma-Travel/NOMA.git` | yes |
| `C:/Noma/console` | `https://github.com/Noma-Travel/console.git` | yes |
| `C:/Noma/system` | `https://github.com/Noma-Travel/system.git` | yes |
| `C:/Noma/noma_scripts` | `https://github.com/Noma-Travel/noma_scripts.git` | yes |
| `C:/Noma/dev/renglo-api` | `https://github.com/Noma-Travel/renglo-api.git` | yes |
| `C:/Noma/dev/renglo-lib` | `https://github.com/Noma-Travel/renglo-lib.git` | yes |
| `C:/Noma/dev/launcher` | `https://github.com/Noma-Travel/launcher.git` | yes |
| `C:/Noma/extensions/wss` | `https://github.com/Noma-Travel/wss.git` | yes |
| `C:/Noma/extensions/inca` | `https://github.com/Noma-Travel/inca.git` | yes |
| `C:/Noma/extensions/pes_noma` | `https://github.com/Noma-Travel/pes_noma.git` | yes |
| `C:/Noma/extensions/noma` | `https://github.com/Noma-Travel/noma_handlers.git` | yes |
| `C:/Noma/extensions/pes` | `https://github.com/renglo/pes.git` | **no** (still upstream `renglo`; migrate when ready) |

## Refresh this table

From PowerShell (same roots as above):

```powershell
$repos = @(
  "C:/Noma/NOMA","C:/Noma/console","C:/Noma/system","C:/Noma/noma_scripts",
  "C:/Noma/dev/renglo-api","C:/Noma/dev/renglo-lib","C:/Noma/dev/launcher",
  "C:/Noma/extensions/wss","C:/Noma/extensions/inca","C:/Noma/extensions/pes",
  "C:/Noma/extensions/pes_noma","C:/Noma/extensions/noma"
)
foreach ($r in $repos) {
  if (Test-Path "$r/.git") {
    $o = git -C $r remote get-url origin 2>$null
    Write-Output "$r`t$o"
  }
}
```

## Notes

- `noma_handlers` is the Noma-Travel home for the former `renglo/noma` extension ([repo](https://github.com/Noma-Travel/noma_handlers)).
- If your local `extensions/noma` branch diverges from `origin/main` on `noma_handlers`, reconcile with `git fetch` / merge or rebase before pushing.
