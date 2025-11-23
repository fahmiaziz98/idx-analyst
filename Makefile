fix:
	ruff check . --fix
	ruff format .

run:
	uv run run.py

generate-key:
	python3 generate_key.py generate

encrypt-key:
	python3 generate_key.py encrypt