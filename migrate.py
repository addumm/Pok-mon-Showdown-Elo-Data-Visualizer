from app import app, db
from sqlalchemy import text

def run_postgres_migrations():
    with app.app_context():
        try:
            print("Running database migrations...")
            
            # PostgreSQL natively supports 'IF NOT EXISTS'
            sql = text("""
                ALTER TABLE replay_cache 
                ADD COLUMN IF NOT EXISTS replay_stats_json TEXT DEFAULT '{}';
            """)
            
            db.session.execute(sql)
            db.session.commit()
            print("PostgreSQL migration completed successfully: Schema updated!")
            
        except Exception as e:
            db.session.rollback()
            print(f"Migration error: {e}")

if __name__ == "__main__":
    run_postgres_migrations()