# RASER Setup: Downloading the Competition Data

The working method is a direct `curl` download of the competition zip into your scratch space using a `KGAT_` API token. It pulls about 21 GB, which took only minutes on the cluster (we saw roughly 170 MB/s).

## What failed for us, so you can skip it

- **Saving into home.** The ICE home quota is 30 GB. The zip stopped at 16 GB with `curl: (23) Failure writing output`.
- **Resuming that truncated file.** `unzip -t` then reported `invalid compressed data` in one entry. Delete a partial file and download fresh.
- **`KAGGLE_USERNAME` / `KAGGLE_KEY` with a `KGAT_` token.** That token type goes in `KAGGLE_API_TOKEN`.
- **`kagglehub` (`UnauthenticatedError`).** It did not pick up our credentials, so we used `curl` instead.

## Before you start

- A Kaggle account that has joined the competition (Step 1).
- About 25 GB free on scratch. ICE scratch allows 300 GB and 1,000,000 files; home allows only 30 GB.

## Step 1: Join the competition

Open https://www.kaggle.com/competitions/gemma-4-developer-agent/rules and click **I Understand and Accept**. Complete phone verification if Kaggle asks. Use the same account for the token in Step 2.

## Step 2: Create an API token

On Kaggle go to your profile, then **Settings**, then **API**, and create a token. It starts with `KGAT_`. Treat it like a password and never commit or paste it.

## Step 3: Add the token to `.env`

```bash
cd ~/raser
cp .env.example .env
chmod 600 .env
```

Make `.env` contain only this line, with no quotes or spaces:

```
KAGGLE_API_TOKEN=KGAT_your_full_token
```

Leave out `KAGGLE_USERNAME` and `KAGGLE_KEY`. `.env` is gitignored.

## Step 4: Point `data/` at your scratch space

Run `pace-quota` and find the **Scratch** path (ours was `/storage/ice1/4/0/dbruce32`). Then:

```bash
D=/storage/ice1/<x>/<y>/<username>/raser-data   # use your own scratch path
mkdir -p "$D"
rmdir ~/raser/data 2>/dev/null                  # removes an empty data/ folder; fails safely if it has files
ln -s "$D" ~/raser/data
ls -l ~/raser/data                              # should show: data -> your scratch path
```

## Step 5: Test the token

```bash
set -a; source .env; set +a
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $KAGGLE_API_TOKEN" https://www.kaggle.com/api/v1/competitions/list
curl -s -L -o /dev/null -w "%{http_code}\n" -r 0-0 -H "Authorization: Bearer $KAGGLE_API_TOKEN" https://www.kaggle.com/api/v1/competitions/data/download-all/gemma-4-developer-agent
```

You want `200` from the first and `200` or `206` from the second. The second call requests one byte, so it does not download the dataset.

## Step 6: Download

Run this inside `tmux` so a dropped SSH session cannot kill it (`tmux new -s download`; detach with `Ctrl+b` then `d`; return with `tmux attach -t download`).

```bash
D=/storage/ice1/<x>/<y>/<username>/raser-data   # same path as Step 4
cd ~/raser
set -a; source .env; set +a
curl -L --fail \
  -H "Authorization: Bearer $KAGGLE_API_TOKEN" \
  -o "$D/gemma-4-developer-agent.zip" \
  https://www.kaggle.com/api/v1/competitions/data/download-all/gemma-4-developer-agent
```

`--fail` stops curl from saving an error page as the zip. If the transfer is interrupted, delete the partial zip and run it again.

## Step 7: Verify, extract, clean up

```bash
ls -lh "$D/gemma-4-developer-agent.zip"        # about 20-21G
unzip -tq "$D/gemma-4-developer-agent.zip"     # must print: No errors detected
unzip -q "$D/gemma-4-developer-agent.zip" -d "$D/gemma-4-developer-agent"
du -sh "$D/gemma-4-developer-agent"            # expect about 21G
find "$D/gemma-4-developer-agent" -type f | wc -l   # expect 524
rm "$D/gemma-4-developer-agent.zip"
```

If `unzip -tq` reports any error, delete the zip and repeat Step 6 from scratch.

## Step 8: Use the data

The files are at `data/gemma-4-developer-agent/` in the repo, which is a symlink to scratch. `data/` is gitignored.

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Step 5 first call returns 401 | Token wrong, revoked, or in the wrong variable | Create a new token and set `KAGGLE_API_TOKEN` |
| First call 200, second call 401 or 403 | Rules not accepted or phone not verified | Redo Step 1 on the same account as the token |
| `curl: (23) Failure writing output` | Out of space, usually writing to home | Check `pace-quota` and download to scratch |
| `unzip`: not a zip file, or invalid compressed data | Truncated or corrupted download | Delete the zip and download fresh without resuming |
| Files gone weeks later | Scratch is purged after inactivity | Download again, or ask PACE about group project storage |

## Team notes

- Each teammate needs their own Kaggle account, token, and rules acceptance.
- Scratch paths differ per user, so everyone sets `D` from their own `pace-quota` output.
- `.env`, `.venv/`, and `data/` must stay in `.gitignore`. If a token is ever committed or shared, revoke it on Kaggle and create a new one.