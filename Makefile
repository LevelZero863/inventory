install:
	python3 -m venv .venv
	. .venv/bin/activate && python -m pip install -U pip && pip install -r requirements.txt

run:
	python -m streamlit run app.py

test:
	python -m unittest discover -s tests -v

backup:
	python scripts/backup.py

check:
	python scripts/check_db.py
