import unittest

from fastapi import HTTPException

from sqlalchemy import create_engine

from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool


from backend_app.database import Base

from backend_app.models.user import User

from backend_app.routers.auth import login,register

from backend_app.schemas.user import LoginRequest,RegisterRequest



class AuthTests(unittest.TestCase):


    @classmethod
    def setUpClass(cls):

        cls.engine=create_engine(
            "sqlite://",
            connect_args={"check_same_thread":False},
            poolclass=StaticPool
        )

        Base.metadata.create_all(
            cls.engine,
            tables=[User.__table__]
        )

        cls.Session=sessionmaker(
            bind=cls.engine
        )


    def setUp(self):

        self.db=self.Session()

        self.db.query(User).delete()

        self.db.commit()


    def tearDown(self):

        self.db.close()


    def register_user(self):

        return register(
            RegisterRequest(
                username="test001",
                password="123456",
                nickname="测试用户"
            ),
            self.db
        )


    def test_register_success_and_password_is_hashed(self):

        response=self.register_user()

        user=self.db.query(User).filter(
            User.username=="test001"
        ).first()

        self.assertEqual(response["code"],200)

        self.assertEqual(response["data"]["user_id"],user.id)

        self.assertEqual(response["data"]["nickname"],"测试用户")

        self.assertNotEqual(user.password,"123456")

        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))


    def test_duplicate_username(self):

        self.register_user()

        with self.assertRaises(HTTPException) as context:

            self.register_user()

        self.assertEqual(context.exception.status_code,409)

        self.assertEqual(context.exception.detail,"用户名已存在")


    def test_login_success(self):

        registered=self.register_user()

        response=login(
            LoginRequest(
                username="test001",
                password="123456"
            ),
            self.db
        )

        self.assertEqual(response["code"],200)

        self.assertEqual(
            response["data"],
            registered["data"]
        )


    def test_wrong_password(self):

        self.register_user()

        with self.assertRaises(HTTPException) as context:

            login(
                LoginRequest(
                    username="test001",
                    password="654321"
                ),
                self.db
            )

        self.assertEqual(context.exception.status_code,401)


    def test_unknown_user(self):

        with self.assertRaises(HTTPException) as context:

            login(
                LoginRequest(
                    username="missing",
                    password="123456"
                ),
                self.db
            )

        self.assertEqual(context.exception.status_code,401)
