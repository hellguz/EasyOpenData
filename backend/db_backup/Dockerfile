FROM postgres:17
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*
COPY backup_script.sh /usr/local/bin/backup_script.sh
RUN chmod +x /usr/local/bin/backup_script.sh

# Add cron job
RUN echo "0 0 * * * root /usr/local/bin/backup_script.sh" >> /etc/crontab

CMD ["cron", "-f"]
