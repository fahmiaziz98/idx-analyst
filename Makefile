fix:
	ruff check . --fix
	ruff format .

run:
	uvicorn src.api.main:app --host 0.0.0.0 --port 7860 --reload --workers 2

generate-key:
	python3 generate_key.py generate

encrypt-key:
	python3 generate_key.py encrypt