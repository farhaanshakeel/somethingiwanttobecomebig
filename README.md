# Tri-angle

Tri-angle is a Discord bot designed to help students form study groups,
manage tasks, and run lightweight productivity features (pomodoro, planner,
profiles). It aims to be easy to run locally and simple to extend via Cogs.

## Quickstart

Prerequisites: Python 3.10+ and `pip`.

1. Create and activate a virtual environment (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Create a `.env` file in the project root with the following values:

```text
DISCORD_TOKEN=your_bot_token_here
# Optional: for faster local slash-command testing
DEV_GUILD_ID=123456789012345678
```

4. Run the bot:

```powershell
python main.py
```

## Configuration

- `DEV_GUILD_ID`: optional guild (server) ID used to sync slash commands to a
	development server quickly during development.
- `DISCORD_TOKEN`: your bot token (required).

## Developer

- Install development tools and register the `pre-commit` hooks:

```powershell
pip install -r requirements.txt
pre-commit install
```

- Run formatters and linters against all files:

```powershell
pre-commit run --all-files
```

### Project layout

- `main.py` — bot entrypoint and cog loader
- `utils.py` — simple JSON-backed persistence helpers
- `cogs/` — Discord Cogs implementing features (study, pomodoro, planner, etc.)
- `triangle_data.json` — runtime data store (created automatically)

## Contributing

Contributions are welcome. Please open issues or pull requests for bugs and
feature suggestions. Follow the existing code style and run the pre-commit
hooks before submitting PRs.

## License

This project is licensed under the MIT License — see the `LICENSE` file.


