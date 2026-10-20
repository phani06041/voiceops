VoiceOps small recovery bundle

This bundle restores the app/models package from the original uploaded VoiceOps project.
It does NOT include or replace .env, the database, or app/main.py.

From the project root (/Users/phanindra/Madmaxx/voiceops 2), extract this ZIP into the project root and allow it to add/replace only:
- app/models/case.py
- app/models/__init__.py
- app/__init__.py

Then verify:
  python -m compileall -q app
  python -c "from app.models.case import CaseQuery, StatusUpdate, ReviewerNote, SpeakRequest; print('models import OK')"

If compileall succeeds and imports work, restart:
  uvicorn app.main:app --reload

Note: this restores the missing model package only. If another app module is missing, stop and inspect the folder tree before copying more files.
