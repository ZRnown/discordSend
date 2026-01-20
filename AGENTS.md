# Repository Guidelines

## Project Structure & Module Organization
- `src/`: React + TypeScript UI (pages in `src/pages/`, app shell in `src/App.tsx`, styles in `src/index.css`).
- `backend/`: Flask API + Discord client, SQLite storage, and scheduling logic (`app.py`, `bot.py`, `database.py`, `auto_sender.py`).
- `src-tauri/`: Tauri Rust host and configuration (`src-tauri/src/main.rs`, `src-tauri/tauri.conf.json`).
- `.github/workflows/`: CI build workflows.

## Build, Test, and Development Commands
- `npm install`: install frontend dependencies.
- `npm run dev`: run the Vite web dev server.
- `npm run tauri dev`: run the full desktop app (frontend + Tauri shell).
- `npm run build` / `npm run preview`: build and preview the web bundle.
- `cd backend && pip install -r requirements.txt`: install backend dependencies.
- `cd backend && python app.py`: start the Flask API for local development.
- `cd backend && pyinstaller --onefile --name backend app.py`: package the Python backend.
- `npm run tauri build`: build the desktop app.

## Coding Style & Naming Conventions
- Frontend uses 2-space indentation, single quotes, and no semicolons (see `src/App.tsx`).
- React components are PascalCase; hooks use `use*` naming.
- Tailwind CSS is the primary styling approach; keep utility class strings readable.
- Backend Python uses 4-space indentation and snake_case for functions/modules.

## Testing Guidelines
- No automated test framework is configured yet.
- Validate changes manually by running the backend (`python app.py`) and the app (`npm run tauri dev`).
- If you add tests, also add scripts to run them and document the workflow here.

## Commit & Pull Request Guidelines
- Git history currently contains a single commit ("first commit"), so there is no established convention.
- Use concise, imperative commit messages (e.g., "add account validation").
- PRs should include a clear description, relevant issue links, and manual test notes; include screenshots for UI changes.

## Security & Configuration Tips
- Runtime settings live in `backend/config.py` (ports, send intervals, thresholds).
- Discord tokens and local data are stored in `backend/data/metadata.db`; never commit tokens or databases.
- When changing API behavior, update any affected frontend calls and note the change in the PR.
