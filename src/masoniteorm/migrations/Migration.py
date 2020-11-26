import os
from os import listdir, path
from os.path import isfile, join
from pydoc import locate

from inflection import camelize

from ..models.MigrationModel import MigrationModel
from ..schema import Schema
from ..connections import ConnectionFactory

from pprint import pprint
from timeit import default_timer as timer


class Migration:
    def __init__(
        self,
        connection="default",
        dry=False,
        command_class=None,
        migration_directory="databases/migrations",
    ):
        self.connection = connection
        self.migration_directory = migration_directory.replace("/", ".")
        self.last_migrations_ran = []
        self.command_class = command_class

        from config.database import DB

        connection_class = db.connection_factory.make(connection)

        DATABASES = db.get_connection_details()

        self.schema = Schema(
            connection=connection_class, connection_details=DATABASES, dry=dry
        ).on(self.connection)

        self.migration_model = MigrationModel.on(self.connection)

    def create_table_if_not_exists(self):
        if not self.schema.has_table("migrations"):
            with self.schema.create("migrations") as table:
                table.increments("migration_id")
                table.string("migration")
                table.integer("batch")

            return True

        return False

    def get_unran_migrations(self):
        directory_path = os.path.join(os.getcwd(), "databases/migrations")
        all_migrations = [
            f
            for f in listdir(directory_path)
            if isfile(join(directory_path, f)) and f != "__init__.py"
        ]
        all_migrations.sort()
        unran_migrations = []
        database_migrations = self.migration_model.all()
        for migration in all_migrations:
            if migration not in database_migrations.pluck("migration"):
                unran_migrations.append(migration)
        return unran_migrations

    def get_rollback_migrations(self):
        return (
            self.migration_model.where("batch", self.migration_model.all().max("batch"))
            .order_by("migration_id", "desc")
            .get()
            .pluck("migration")
        )

    def get_all_migrations(self, reverse=False):
        if reverse:
            return (
                self.migration_model.order_by("migration_id", "desc")
                .get()
                .pluck("migration")
            )

        return self.migration_model.all().pluck("migration")

    def get_last_batch_number(self):
        return self.migration_model.select("batch").get().max("batch")

    def delete_migration(self, file_path):
        return self.migration_model.where("migration", file_path).delete()

    def locate(self, file_name):
        migration_name = camelize("_".join(file_name.split("_")[4:]).replace(".py", ""))
        file_name = file_name.replace(".py", "")
        return locate(f"{self.migration_directory}.{file_name}.{migration_name}")

    def get_ran_migrations(self):
        directory_path = os.path.join(os.getcwd(), "databases/migrations")
        all_migrations = [
            f
            for f in listdir(directory_path)
            if isfile(join(directory_path, f)) and f != "__init__.py"
        ]
        all_migrations.sort()
        ran = []

        database_migrations = self.migration_model.all()
        for migration in all_migrations:
            if migration in database_migrations.pluck("migration"):
                ran.append(migration)
        return ran

    def migrate(self, output=False):
        batch = self.get_last_batch_number() + 1

        for migration in self.get_unran_migrations():
            migration_module = migration.replace(".py", "")
            migration_name = camelize(
                "_".join(migration.split("_")[4:]).replace(".py", "")
            )
            migration_class = locate(
                f"{self.migration_directory}.{migration_module}.{migration_name}"
            )
            self.last_migrations_ran.append(migration)
            if self.command_class:
                self.command_class.line(
                    f"<comment>Migrating:</comment> <question>{migration}</question>"
                )

            migration_class = migration_class(connection=self.connection)

            if output:
                migration_class.schema.dry()
            start = timer()
            migration_class.up()
            duration = "{:.2f}".format(timer() - start)

            if output:
                if self.command_class:
                    table = self.command_class.table()
                    table.set_header_row(["SQL"])
                    table.set_rows([[migration_class.schema._blueprint.to_sql()]])
                    table.render(self.command_class.io)
                    continue
                else:
                    print(migration_class.schema._blueprint.to_sql())

            if self.command_class:
                self.command_class.line(
                    f"<info>Migrated:</info> <question>{migration}</question> ({duration}s)"
                )

            self.migration_model.create({"batch": batch, "migration": migration})

    def rollback(self, output=False):
        for migration in self.get_rollback_migrations():
            if self.command_class:
                self.command_class.line(
                    f"<comment>Rolling back:</comment> <question>{migration}</question>"
                )

            migration_class = self.locate(migration)(connection=self.connection)

            if output:
                migration_class.schema.dry()

            start = timer()
            migration_class.down()
            duration = "{:.2f}".format(timer() - start)

            if output:
                if self.command_class:
                    table = self.command_class.table()
                    table.set_header_row(["SQL"])
                    if (
                        hasattr(migration_class.schema, "_blueprint")
                        and migration_class.schema._blueprint
                    ):
                        table.set_rows([[migration_class.schema._blueprint.to_sql()]])
                    elif migration_class.schema._sql:
                        table.set_rows([[migration_class.schema._sql]])
                    table.render(self.command_class.io)
                    continue
                else:
                    print(migration_class.schema._blueprint.to_sql())

            self.delete_migration(migration)

            if self.command_class:
                self.command_class.line(
                    f"<info>Rolled back:</info> <question>{migration}</question> ({duration}s)"
                )

    def rollback_all(self):
        ran_migrations = []
        for migration in self.get_all_migrations():
            self.locate(migration)().down()
            self.delete_migration(migration)
            ran_migrations.append(migration)

        self.delete_migrations(ran_migrations)

    def delete_migrations(self, migrations=[]):
        return self.migration_model.where_in("migration", migrations).delete()

    def delete_last_batch(self):
        return self.migration_model.where(
            "batch", self.get_last_batch_number()
        ).delete()

    def reset(self):
        for migration in self.get_all_migrations(reverse=True):
            if self.command_class:
                self.command_class.line(
                    f"<comment>Rolling back:</comment> <question>{migration}</question>"
                )

            self.locate(migration)(connection=self.connection).down()

            self.delete_migration(migration)

            if self.command_class:
                self.command_class.line(
                    f"<info>Rolled back:</info> <question>{migration}</question>"
                )

            self.delete_migrations([migration])

        if self.command_class:
            self.command_class.line("")

    def refresh(self):
        self.reset()
        self.migrate()
