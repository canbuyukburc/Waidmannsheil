#!/bin/bash

# Wait for database and initialize it
echo "Initializing database..."
python init_db.py

if [ $? -eq 0 ]; then
    echo "Database initialized successfully. Starting application..."
    exec gunicorn --bind 0.0.0.0:5000 app:app
else
    echo "Database initialization failed!"
    exit 1
fi