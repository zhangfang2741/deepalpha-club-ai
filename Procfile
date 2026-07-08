release: /app/.venv/bin/python -c "import alembic.config; alembic.config.main()" upgrade head
web: /app/.venv/bin/python -c "import os,uvicorn; uvicorn.run('app.main:app', host='0.0.0.0', port=int(os.environ.get('PORT',8000)))"
worker: /app/.venv/bin/celery -A app.core.celery_app worker --loglevel=info -Q supply_chain
beat: /app/.venv/bin/celery -A app.core.celery_app beat --loglevel=info
