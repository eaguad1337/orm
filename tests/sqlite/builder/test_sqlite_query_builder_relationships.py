import inspect
import unittest

from src.masoniteorm.orm.query import QueryBuilder
from src.masoniteorm.orm.query.grammars import SQLiteGrammar
from src.masoniteorm.orm.connections import ConnectionFactory
from src.masoniteorm.orm.models import Model
from src.masoniteorm.orm.relationships import belongs_to
from tests.utils import MockConnectionFactory


class Logo(Model):
    __connection__ = "sqlite"


class Article(Model):
    __connection__ = "sqlite"

    @belongs_to("id", "article_id")
    def logo(self):
        return Logo


class Profile(Model):
    __connection__ = "sqlite"


class User(Model):
    __connection__ = "sqlite"

    @belongs_to("id", "user_id")
    def articles(self):
        return Article

    @belongs_to("id", "user_id")
    def profile(self):
        return Profile


class BaseTestQueryRelationships(unittest.TestCase):

    maxDiff = None

    def get_builder(self, table="users"):
        connection = MockConnectionFactory().make("sqlite")
        return QueryBuilder(
            grammar=SQLiteGrammar, connection=connection, table=table, model=User
        )

    def test_has(self):
        builder = self.get_builder()
        sql = builder.has("articles").to_sql()
        self.assertEqual(
            sql,
            """SELECT * FROM "users" WHERE EXISTS ("""
            """SELECT * FROM "articles" WHERE "articles"."user_id" = "users"."id\""""
            """)""",
        )

    def test_where_has_query(self):
        builder = self.get_builder()
        sql = builder.where_has("articles", lambda q: q.where("active", 1)).to_sql()
        self.assertEqual(
            sql,
            """SELECT * FROM "users" WHERE EXISTS ("""
            """SELECT * FROM "articles" WHERE "articles"."user_id" = "users"."id" AND "articles"."active" = '1'"""
            """)""",
        )

    def test_relationship_multiple_has(self):
        to_sql = User.has("articles", "profile").to_sql()
        self.assertEqual(
            to_sql,
            """SELECT * FROM "users" WHERE EXISTS ("""
            """SELECT * FROM "articles" WHERE "articles"."user_id" = "users"."id\""""
            """) AND EXISTS ("""
            """SELECT * FROM "profiles" WHERE "profiles"."user_id" = "users"."id\""""
            """)""",
        )

    def test_relationship_multiple_has_calls(self):
        to_sql = User.has("articles").has("profile").to_sql()
        self.assertEqual(
            to_sql,
            """SELECT * FROM "users" WHERE EXISTS ("""
            """SELECT * FROM "articles" WHERE "articles"."user_id" = "users"."id\""""
            """) AND EXISTS ("""
            """SELECT * FROM "profiles" WHERE "profiles"."user_id" = "users"."id\""""
            """)""",
        )

    def test_nested_has(self):
        to_sql = User.has("articles.logo").to_sql()
        self.assertEqual(
            to_sql,
            """SELECT * FROM "users" WHERE EXISTS (SELECT * FROM "articles" WHERE "articles"."user_id" = "users"."id" AND EXISTS (SELECT * FROM "logos" WHERE "logos"."article_id" = "articles"."id"))""",
        )
