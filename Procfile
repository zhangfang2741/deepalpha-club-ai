release: /app/.venv/bin/python -c "import alembic.config; alembic.config.main()" upgrade head
web: bash /app/scripts/start_web_with_worker.sh
worker: /app/.venv/bin/celery -A app.core.celery_app worker --loglevel=info -Q supply_chain,supply_chain_orchestration
beat: /app/.venv/bin/celery -A app.core.celery_app beat --loglevel=info
