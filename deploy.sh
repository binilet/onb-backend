#!/bin/bash
#cd "$(dirname "$0")"
#export PYTHONPATH=$(pwd)
#source venv/bin/activate
#exec gunicorn app.main:app \
#  -w 2 \
#  -k uvicorn.workers.UvicornWorker \
#  --bind 127.0.0.1:8001 \
#  --timeout 60 \
#  --log-level info

#run the above script with pm2 with the following command
#pm2 start ./start-fastapi.sh --name fastapi-admin

#testing api using uvicorn
#uvicorn main:app --reload --host 0.0.0.0 --port 8001

#copy folder and files to vps
mv ./backend/app/.env ./backend/app/.env.bak
scp -r ./backend/app/* root@138.68.90.48:/onbingo-admin/admin-dashboard/app/
mv ./backend/app/.env.bak ./backend/app/.env

