FROM aries-missionops:m2-rollback
COPY --chown=missionops:missionops scripts/backup_sqlite.py /app/scripts/backup_sqlite.py