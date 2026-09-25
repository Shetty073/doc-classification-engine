import asyncio
import logging
from sqlalchemy import select
from app.database import AsyncSessionLocal, init_db
from app.models import User
from app.security import get_password_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")


async def seed_data():
    """Initializes tables and creates default banking operator user if missing."""
    logger.info("Initializing database schema...")
    await init_db()

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User).where(User.username == "admin"))
        existing_admin = result.scalars().first()

        if existing_admin:
            logger.info("Admin user already exists (id=%s).", existing_admin.id)
            return

        admin_user = User(
            username="admin",
            hashed_password=get_password_hash("admin_secure_pass123"),
            is_active=True,
        )
        session.add(admin_user)
        await session.commit()
        logger.info("Default banking operator user created: username='admin', password='admin_secure_pass123'")


if __name__ == "__main__":
    asyncio.run(seed_data())
