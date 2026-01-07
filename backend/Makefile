fix:
	uv run ruff check . --fix
	uv run ruff format .

run:
	uv run uvicorn src.api.main:app --host 0.0.0.0 --port 7860 --reload --workers 2

generate-key:
	uv run python3 generate_key.py generate

encrypt-key:
	uv run python3 generate_key.py encrypt

run-test:
	uv run pytest tests/ -vv