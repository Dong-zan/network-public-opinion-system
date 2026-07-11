from sqlalchemy import create_engine

from sqlalchemy.orm import (
    sessionmaker,
    declarative_base
)

from backend_app.config import settings



DATABASE_URL = (
    f"mysql+pymysql://"
    f"{settings.MYSQL_USER}:"
    f"{settings.MYSQL_PASSWORD}@"
    f"{settings.MYSQL_HOST}:"
    f"{settings.MYSQL_PORT}/"
    f"{settings.MYSQL_DATABASE}"
)



engine = create_engine(
    DATABASE_URL,
    echo=True,
    pool_pre_ping=True
)



SessionLocal=sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)



Base=declarative_base()



def get_db():

    db=SessionLocal()

    try:

        yield db

    finally:

        db.close()