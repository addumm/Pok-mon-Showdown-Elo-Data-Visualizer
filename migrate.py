from app import app, db
from sqlalchemy import text

def run_postgres_migrations():
    with app.app_context():
        try:
            print("Running database migrations...")

            # ensure any newly defined models/tables in models.py (e.g., GameAnalysis) are created
            db.create_all()
            print("Checked table creation for all models.")

            # apply schema ALTER statements for existing tables
            migrations = [
                "ALTER TABLE replay_cache ADD COLUMN IF NOT EXISTS replay_stats_json TEXT DEFAULT '{}';",
                # Add any additional ALTER statements here if existing table schemas changed
            ]

            for statement in migrations:
                db.session.execute(text(statement))

            db.session.commit()
            print("PostgreSQL migrations completed successfully!")

        except Exception as e:
            db.session.rollback()
            print(f"Migration error: {e}")

if __name__ == "__main__":
    run_postgres_migrations()