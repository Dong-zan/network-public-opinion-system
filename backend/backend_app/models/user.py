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
        unique=True
    )


    password=Column(
        String(100)
    )


    preferences=Column(
        JSON
    )