from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    MYSQL_HOST:str

    MYSQL_PORT:int

    MYSQL_USER:str

    MYSQL_PASSWORD:str

    MYSQL_DATABASE:str

    AI_SERVER_URL:str

    APP_NAME:str


    class Config:

        env_file=".env"



settings = Settings()