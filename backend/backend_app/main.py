from fastapi import FastAPI


from backend_app.database import (
    Base,
    engine
)


from backend_app import models


from backend_app.config import settings


from backend_app.internal import articles
from backend_app.internal import analysis
from backend_app.internal import ai_input


from backend_app.routers import events
from backend_app.routers import news
from backend_app.routers import ai
from backend_app.routers import auth
from backend_app.routers import user



Base.metadata.create_all(
    bind=engine
)



app = FastAPI(

    title=settings.APP_NAME,

    version="1.0.0"

)



app.include_router(

    articles.router

)



app.include_router(

    analysis.router

)



app.include_router(

    events.router

)



app.include_router(

    news.router

)



app.include_router(

    news.event_news_router

)



app.include_router(

    ai.router

)



app.include_router(

    auth.router

)



app.include_router(

    user.router

)



app.include_router(

    ai_input.router

)




@app.get("/")
def index():


    return {


        "system":
            settings.APP_NAME,


        "status":
            "running"

    }
