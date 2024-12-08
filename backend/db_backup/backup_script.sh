#!/bin/bash

BACKUP_DIR=/backups
mkdir -p $BACKUP_DIR
export PGPASSWORD="barcelona"

# Create a new backup
NEW_BACKUP=$BACKUP_DIR/backup_$(date +%Y-%m-%d_%H-%M-%S).dump
pg_dump -U postgres -h postgis -F c easyopendata_database > $NEW_BACKUP

# Check if the backup was successful
if [ $? -eq 0 ]; then
    echo "Backup created: $NEW_BACKUP"
else
    echo "Backup failed!" >&2
    exit 1
fi

# Delete old backups, keeping only the last 3
NUM_BACKUPS_TO_KEEP=3
BACKUP_COUNT=$(ls -1 $BACKUP_DIR | wc -l)

if [ $BACKUP_COUNT -gt $NUM_BACKUPS_TO_KEEP ]; then
    echo "Cleaning up old backups..."
    ls -1t $BACKUP_DIR | tail -n +$(($NUM_BACKUPS_TO_KEEP + 1)) | while read OLD_BACKUP; do
        rm -f "$BACKUP_DIR/$OLD_BACKUP"
        echo "Deleted old backup: $BACKUP_DIR/$OLD_BACKUP"
    done
fi
