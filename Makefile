load:
	docker compose run --rm app uv run python scripts/load_daily.py

ui:
	docker compose up streamlit

shell:
	docker compose run --rm app bash

test:
	docker compose run --rm app uv run pytest
