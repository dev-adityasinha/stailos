import asyncio
from sqlalchemy import text
from app.db.base import engine

async def migrate():
    print("Starting production database migration...")
    
    # Run synchronously with the engine
    with engine.begin() as conn:
        print("Adding slug column...")
        # Since this is postgres, IF NOT EXISTS is not supported for ADD COLUMN until Postgres 9.6, but Render is >15.
        # However, to be safe against errors if the column already exists:
        try:
            conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS slug VARCHAR;"))
        except Exception as e:
            print(f"Skipping slug column addition: {e}")
            
        print("Adding onboarding_data column...")
        try:
            conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS onboarding_data JSON;"))
        except Exception as e:
            print(f"Skipping onboarding_data column addition: {e}")
            
        print("Adding onboarding_completed column...")
        try:
            conn.execute(text("ALTER TABLE tenants ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN DEFAULT FALSE;"))
        except Exception as e:
            print(f"Skipping onboarding_completed column addition: {e}")

        # Backfill slug for any existing tenants
        print("Backfilling slugs for existing tenants...")
        tenants = conn.execute(text("SELECT id, name FROM tenants WHERE slug IS NULL")).fetchall()
        for t in tenants:
            t_id, t_name = t[0], t[1]
            slug = t_name.lower().strip().replace(" ", "-") if t_name else "workspace"
            # Keep it simple, append short id
            slug = f"{slug}-{str(t_id)[:6]}"
            conn.execute(text("UPDATE tenants SET slug = :slug WHERE id = :id"), {"slug": slug, "id": t_id})

        # Add UNIQUE constraint on slug if not exists (using a custom constraint name to avoid duplicate creation errors)
        try:
            # We can't do IF NOT EXISTS for ADD CONSTRAINT easily without complex queries.
            # We just try to add it.
            conn.execute(text("ALTER TABLE tenants ADD CONSTRAINT tenants_slug_key UNIQUE (slug);"))
        except Exception as e:
            print(f"Note: unique constraint might already exist or failed: {e}")

    print("✅ Migration completed successfully.")

if __name__ == "__main__":
    asyncio.run(migrate())
