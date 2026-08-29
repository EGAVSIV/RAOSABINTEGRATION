# RaoSab Trading Rulebook

The public rulebook is `rulebook/index.html` and is served by GitHub Pages.

Saving is handled by a separate Vercel serverless API in `api/rulebook.js`. The browser **never receives or asks for a GitHub PAT**.

## Vercel setup

Import this GitHub repository into a Vercel project. Vercel supports importing an existing GitHub repository from **Add New → Project → Import**. The API file is `api/rulebook.js`. citeturn1search1

Create these Production environment variables in the Vercel project:

- `GITHUB_TOKEN` — fine-grained GitHub token for `EGAVSIV/RAOSABINTEGRATION` with **Contents: Read and write**.
- `RULEBOOK_PASSWORD` — your private Rulebook admin password.
- `RULEBOOK_SESSION_SECRET` — a long random secret used to sign the HttpOnly admin session cookie.

After deployment, set the `API_URL` in `rulebook/index.html` to the deployed Vercel function URL:

`https://YOUR-VERCEL-PROJECT.vercel.app/api/rulebook`

The GitHub token remains only in Vercel's server environment; it is never embedded in the GitHub Pages HTML.

## Files

- `rulebook/index.html` — Rulebook UI
- `rulebook/rules.json` — rule database
- `rulebook/uploads/images/` — uploaded images
- `rulebook/uploads/pdf/` — uploaded PDFs
- `api/rulebook.js` — secure server-side writer
- `vercel.json` — Vercel Function configuration

## Upload limit

The API accepts files up to 3 MB each. This is intentional because Vercel Functions impose request payload limits; larger files should use direct object storage rather than passing the file through the Function. citeturn0search1
