#!/usr/bin/env python3
"""Database initialization script"""

import os
import time
from app import app, db, User, Environment, UserEnvironment

def wait_for_db(max_retries=30):
    """Wait for database to be available"""
    for i in range(max_retries):
        try:
            with app.app_context():
                # Test database connection
                result = db.session.execute(db.text('SELECT 1'))
                result.fetchone()
            print("Database is ready!")
            return True
        except Exception as e:
            print(f"Waiting for database... ({i+1}/{max_retries}): {str(e)}")
            time.sleep(2)
    return False

def init_database():
    """Initialize database tables and create admin user"""
    with app.app_context():
        # Create all tables
        db.create_all()
        print("Database tables created!")
        
        # Create default system admin if not exists
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(username='admin', email='admin@example.com', is_system_admin=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.flush()  # To get the admin.id
            
            # Create a demo user to be the environment admin
            demo_user = User.query.filter_by(username='hunter').first()
            if not demo_user:
                demo_user = User(username='hunter', email='hunter@example.com')
                demo_user.set_password('hunter123')
                db.session.add(demo_user)
                db.session.flush()
            
            # Create default environment
            default_env = Environment(
                name="Hunter's Meat Shop",
                description="Default environment for meat sales management",
                admin_id=demo_user.id  # Demo user is the environment creator
            )
            db.session.add(default_env)
            db.session.flush()  # To get the env.id
            
            # Add demo user as environment admin
            demo_env = UserEnvironment(
                user_id=demo_user.id,
                environment_id=default_env.id,
                role='envadm'
            )
            db.session.add(demo_env)
            
            db.session.commit()
            print("System admin and demo environment created!")
            print(f"System Admin: admin/admin123")
            print(f"Demo Environment Admin: hunter/hunter123")
            print(f"Environment invite code: {default_env.invite_code}")
        else:
            # Update existing admin to be system admin
            if not admin.is_system_admin:
                admin.is_system_admin = True
                db.session.commit()
                print("Updated existing admin to system admin.")
            else:
                print("System admin already exists.")

if __name__ == '__main__':
    print("Starting database initialization...")
    if wait_for_db():
        init_database()
        print("Database initialization complete!")
    else:
        print("Failed to connect to database!")
        exit(1)