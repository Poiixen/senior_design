# Automatic updates from main

The `CI` workflow tests the exact commit, builds both images on GitHub, and
streams them to `167.99.145.105`. It deploys only pushes to `main` when the
repository variable `AUTO_DEPLOY` is `true`. Pull requests never deploy.
Manual runs on `main` run the same tests and default to preparation only.

The server directory remains `/root/team-science`; the existing `.env`, SQLite,
uploaded datasets, and Caddy volumes remain in place. Images use commit SHA
tags. No registry login or application password is needed in GitHub.

## One-time GitHub connection

Repository Settings → Secrets and variables → Actions:

| Kind | Name | Value |
| --- | --- | --- |
| Secret | `DEPLOY_SSH_KEY` | Dedicated deployment private key |
| Secret | `DEPLOY_KNOWN_HOSTS` | Previously verified SSH host-key entries |
| Variable | `DEPLOY_HOST` | `167.99.145.105` |
| Variable | `DEPLOY_USER` | `root` |
| Variable | `AUTO_DEPLOY` | `false` until first activation succeeds |

These were configured during setup. The matching public key is installed with
SSH's `restrict` option (no forwarding or PTY). It can still run server commands;
treat write access to `main` and this workflow as production access. Require
reviewed PRs and passing CI on `main` in repository branch rules. A repository
administrator may need to configure those rules. The existing SSH firewall
must permit GitHub-hosted runners; if it restricts source IPs, use a runner with
a stable address rather than opening SSH broadly.

## First release and passwords

1. Review and merge the pending app changes and deployment workflow into `main`.
   Automatic deployment is still disabled.
2. Open GitHub → Actions → **CI** → **Run workflow**. Select `main` and leave
   **prepare_only** checked. Wait for the build/transfer job to finish. Its run
   summary contains the full release SHA. A CLI equivalent is:

   ```bash
   gh workflow run ci.yml --repo Poiixen/senior_design --ref main -f prepare_only=true
   ```

3. Open your normal interactive server terminal (`ssh root@167.99.145.105`).
   Run the following, replacing the SHA with the run summary's 40-character SHA:

   ```bash
   cd /root/team-science
   RELEASE=PASTE_THE_FULL_RELEASE_SHA
   bash .incoming/$RELEASE/deploy/activate-first-release.sh "$RELEASE"
   ```

   This backs up the app data, stops the API briefly, and asks for two different
   passwords of at least 15 characters. Password entry is hidden and only Argon2
   hashes are stored. Keep them in your password manager. It then activates the
   prepared release. If password setup fails, the previous API is restarted.
   Existing uploaded data is preserved. Demo access is read-only; admin has its
   own upload/report workspace. No SMTP setup is necessary.

4. Open `https://spteamscience.com/login`. Check both passwords, confirm demo
   reports open and admin can upload, then log out. Verify the actual site
   domain against the server's `.env` if it differs.
5. Change the repository variable `AUTO_DEPLOY` to `true`:

   ```bash
   gh variable set AUTO_DEPLOY --repo Poiixen/senior_design --body true
   ```

Future merges into `main` now test → build → transfer → back up → restart →
check `/health` and `/login`. Setting the variable to `false` pauses automatic
deployments. Manual runs with `prepare_only` unchecked still deploy.

## Recovery and maintenance

`deploy/apply-release.sh` serializes deployments with a server lock. It stops
writers before copying SQLite and Parquet together, checks both shared accounts
exist, and records a successful SHA in `.deployed-commit`. Failed startup or
public HTTPS checks restore the old application images/configuration. Database
changes are not automatically undone: inspect and restore the backup manually
if a future incompatible migration requires it. Code rollback is not a promise
of database compatibility.

The latest three data archives remain under `backups/`; copy them off-server.
Old commit image tags are removed after success, retaining current/rollback
images. Monitor free disk space. Never delete the application data volume.

After automation is active, manual Compose commands must also load the image
selection file, for example:

```bash
docker compose --env-file .env --env-file .release.env -f compose.small.yaml ps
docker compose --env-file .env --env-file .release.env -f compose.small.yaml logs --tail=50
```

References: [GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax),
[Compose environment files](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/),
[Compose startup health checks](https://docs.docker.com/reference/cli/docker/compose/up/).
