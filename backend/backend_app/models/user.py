from sqlalchemy import Column,Integer,String,JSON


from backend_app.database import Base



class User(Base):


    __tablename__="users"



    id=Column(
        Integer,
        primary_key=True
    )


    username=Column(
        String(50),
        unique=True,
        nullable=False
    )


    nickname=Column(
        String(50),
        nullable=False
    )


    password=Column(
        String(255),
        nullable=False
    )


    preferences=Column(
        JSON
    )
