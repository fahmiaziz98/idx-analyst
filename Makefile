fix:
	ruff check . --fix
	ruff format .

run_graph:
	uv run src/test_graph.py