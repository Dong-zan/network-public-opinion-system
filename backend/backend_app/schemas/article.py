from pydantic import BaseModel

from typing import Optional



class ArticleCreate(BaseModel):

    title:str


    content:Optional[str]=None


    source:Optional[str]=None


    url:Optional[str]=None


    publish_time:Optional[str]=None


    platform:Optional[str]=None


    author:Optional[str]=None


    account_id:Optional[str]=None


    account_name:Optional[str]=None


    account_type:Optional[str]=None


    is_official:Optional[bool]=False


    repost_count:Optional[int]=0


    comment_count:Optional[int]=0


    like_count:Optional[int]=0