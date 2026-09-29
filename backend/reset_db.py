import os
from sqlalchemy import create_engine, text
from app.db.base import Base
from app.main import import_all_models

def reset_db():
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("Error: DATABASE_URL environment variable is not set.")
        return
        
    print(f"Connecting to database: {url.split('@')[-1]}")
    engine = create_engine(url)
    
    import_all_models()
    
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    
    print("Recreating tables...")
    Base.metadata.create_all(bind=engine)
    
    print("Database reset successfully. You can now run the seed script to populate demo data.")

if __name__ == "__main__":
    reset_db()
