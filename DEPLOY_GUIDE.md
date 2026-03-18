# Zappa Deployment Guide

## Production deploy (noma_prod)

To deploy the backend with **latest renglo-lib and extensions/noma** (e.g. after tool-install-on-org-creation changes):

```bash
cd system
source venv/bin/activate   # or: .\venv\Scripts\activate on Windows

# Refresh local packages so deploy uses current renglo-lib + noma
pip install -r requirements.txt

# Deploy (first time: use "deploy"; subsequent: use "update")
./zappa_deploy.sh noma_prod update
# Or force clean build: ./zappa_deploy.sh noma_prod update --clean
```

After redeploying you can delete all users and test the full flow; new organizations will get NOMA and SCHD tools installed automatically on creation.

---

## How Environment Matching Works

The `zappa_deploy.sh` script ensures your deployment environment **exactly matches** your dev environment using this process:

### 1. **Exact Version Capture**
```bash
pip freeze --exclude-editable > .freeze.txt
```
This captures **exact versions** of all non-editable packages:
```
boto3==1.35.36
flask==3.0.3
anthropic==0.40.0
```

### 2. **Download Exact Wheels**
```bash
pip download -r .freeze.txt -d .wheelhouse
```
Downloads the **exact same wheels** that are in your environment. No version resolution, no surprises.

### 3. **Build Local Package Wheels**
```bash
pip wheel ../dev/renglo-api/renglo_api -w .wheelhouse
pip wheel ../dev/renglo-lib/renglo -w .wheelhouse
pip wheel ../extensions/noma/package/noma -w .wheelhouse
```
Builds wheels from your editable installs at their **current state**.

### 4. **Install from Wheels Only**
```bash
pip install --no-index --find-links .wheelhouse <package>
```
- `--no-index`: Don't use PyPI (only use wheelhouse)
- `--find-links .wheelhouse`: Only use our wheelhouse
- **Result**: Impossible to install different versions

## Usage

```bash
cd system

# Activate your dev venv
source venv/bin/activate

# Deploy (first time)
./zappa_deploy.sh noma_prod deploy

# Update (subsequent deploys - FAST, reuses wheelhouse)
./zappa_deploy.sh noma_prod update

# Update with clean build (fresh download of all packages)
./zappa_deploy.sh noma_prod update --clean
```

### When to Use `--clean`

Use the `--clean` flag when:
- You've upgraded PyPI packages and want to ensure fresh downloads
- Troubleshooting deployment issues
- First deploy on a new machine

Normal updates reuse the wheelhouse for speed (30 sec vs 2-3 min).

## What Happens

```
Your Dev Environment          Wheelhouse              Deployment Venv
━━━━━━━━━━━━━━━━━━━          ━━━━━━━━━━              ━━━━━━━━━━━━━━━
boto3==1.35.36      ────┐     .wheelhouse/           boto3==1.35.36
flask==3.0.3        ────┼────► boto3-1.35.36.whl ───► flask==3.0.3
anthropic==0.40.0   ────┘     flask-3.0.3.whl        anthropic==0.40.0
                              anthropic-0.40.0.whl
                              
renglo_api (editable) ──┐     renglo_api-1.0.0.whl ─► renglo_api==1.0.0
renglo (editable) ──────┼────► renglo-1.0.0.whl ─────► renglo==1.0.0
noma (editable) ────────┘     noma-1.0.0.whl ────────► noma==1.0.0

                    Same versions    Same wheels    Exact match!
```

## Why This Works

1. **No version resolution**: We don't ask pip to resolve dependencies, we give it exact versions
2. **No PyPI access during install**: Can't accidentally get newer versions
3. **Wheels are binary**: Compiled once, installed identically
4. **Checksums**: Wheels include checksums, guaranteeing file integrity

## Advantages Over pip-compile

| pip-compile | Our Approach |
|------------|--------------|
| Requires pip-tools | No extra dependencies |
| Can have compatibility issues | Pure pip/wheel |
| Resolves dependencies (slower) | Uses frozen state (faster) |
| Generates hash file | Uses wheels directly |

## Speed Optimization

The script **automatically preserves** the wheelhouse between deployments:
- First deploy: ~2-3 min (downloads all packages)
- Subsequent deploys: ~30 sec (reuses wheelhouse)
- Local package changes: Always detected and included

The script automatically:
- ✅ Regenerates freeze file (detects version changes)
- ✅ Detects your local package changes
- ✅ Keeps wheelhouse for speed
- ✅ Cleans up deployment venv

To force fresh download:
```bash
./zappa_deploy.sh noma_prod update --clean
```

## Troubleshooting

### "ERROR: Not in a virtualenv"
```bash
cd system
source venv/bin/activate
./zappa_deploy.sh noma_prod update
```

### "Editable installs detected"
This means the script found editables in the deployment venv (shouldn't happen).
Check the error output and ensure you're not modifying `pip install` commands.

### Package Version Mismatch
If you update a package in dev:
```bash
cd system
source venv/bin/activate
pip install --upgrade <package>
./zappa_deploy.sh noma_prod update --clean  # Force refresh
```

### Deployment Failed with 502
Check Lambda logs:
```bash
source venv/bin/activate
zappa tail noma_prod
```

Common causes:
- Missing environment variables in `zappa_settings.json`
- Import errors (check CloudWatch logs)
- Configuration issues

## Files Created & Cleanup

The script automatically manages these files:

| File | Purpose | Lifecycle |
|------|---------|-----------|
| `.freeze.txt` | Frozen package versions | Auto-deleted and regenerated each run |
| `.wheelhouse/` | Downloaded wheels | **Kept between runs** for speed |
| `.venv_deploy/` | Clean deployment venv | Auto-deleted after deploy |

**You don't need to manually clean anything!** The script handles it automatically.

Use `--clean` flag only when you want to force fresh package downloads.

## Clean Deployment Guarantee

The script **guarantees** no editable installs in deployment:
- Step 3: Detects editables in dev
- Step 6: Builds them into wheels
- Step 10: **Verifies** no editables in deployment venv

If Step 10 fails, deployment is aborted.

