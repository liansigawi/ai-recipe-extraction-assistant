"""Migrations bring a database up to date without losing anything.

A "milestone 3 database" here is built from tests/fixtures/milestone3_schema.sql: the exact
tables milestone 3 created before migrations existed, filled with recipes like yours.
"""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient

from app.db import Base
from app.main import app
from app.migrate import alembic_config, head_revision, migration_engine, upgrade_database
from app.sample_data import STARTER_CATEGORIES

FIXTURE = Path(__file__).parent / "fixtures" / "milestone3_schema.sql"
STARTER = dict(STARTER_CATEGORIES)


def table_definitions(path: Path) -> list[str]:
    """Each table's CREATE statement, with spacing normalized (alembic's own table left out)."""
    with closing(sqlite3.connect(path)) as db:
        rows = db.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name != 'alembic_version' ORDER BY name"
        ).fetchall()
    return [" ".join(sql.split()) for (sql,) in rows]


def milestone3_definitions() -> list[str]:
    lines = [line for line in FIXTURE.read_text(encoding="utf-8").splitlines() if not line.startswith("--")]
    return [" ".join(statement.split()) for statement in "\n".join(lines).split(";") if statement.strip()]


def make_milestone3_database(path: Path) -> None:
    """A milestone-3 database with categories, a sample, a recipe of your own and its source."""
    with closing(sqlite3.connect(path)) as db:
        db.executescript(FIXTURE.read_text(encoding="utf-8"))
        db.executemany(
            "INSERT INTO categories (id, name, description, parent_id) VALUES (?, ?, ?, NULL)",
            [(1, "קינוחים", None), (2, "בישולים", None), (3, "ארוחות קלילות", None)],
        )
        db.execute(
            "INSERT INTO recipes VALUES (1, 'עוגת שוקולד עם גנאש', 1, NULL, '12 פרוסות', ?, '[]', '[]', 1, "
            "'2026-10-20 06:07:07.769970', '2026-10-20 06:07:07.769970')",
            ('[{"name": null, "ingredients": [{"text": "200 גרם שוקולד מריר", "quantity": "200 גרם"}]}]',),
        )
        db.execute(
            "INSERT INTO recipes VALUES (2, 'בדיקה', NULL, NULL, NULL, '[]', ?, '[\"הערה\"]', 0, "
            "'2026-10-20 06:09:43.829564', '2026-10-20 06:15:00.000000')",
            ('[{"name": null, "steps": ["מערבבים."]}]',),
        )
        db.execute("INSERT INTO recipe_sources VALUES (1, 2, 0, 'manual', NULL, '[\"me\"]')")
        db.commit()


def test_migration_0001_creates_exactly_the_milestone_3_tables(tmp_path):
    path = tmp_path / "recipes.db"
    engine = migration_engine(path)
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), "0001")
    engine.dispose()
    assert table_definitions(path) == milestone3_definitions()


def test_a_new_database_gets_every_migration_and_matches_the_models(tmp_path):
    path = tmp_path / "recipes.db"
    result = upgrade_database(path)
    assert result.created and result.backup is None and result.to_revision == head_revision()

    engine = migration_engine(path)
    with engine.connect() as connection:
        # What `alembic revision --autogenerate` would find: no difference between the tables and app/models.py.
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    engine.dispose()


def test_a_milestone_3_database_is_upgraded_and_keeps_every_recipe(data_dir):
    database = data_dir / "recipes.db"
    make_milestone3_database(database)

    with TestClient(app, base_url="http://localhost") as client:
        recipes = client.get("/api/recipes").json()
        # Not seeded again: the database already existed. (0005 renamed one category and added the drinks.)
        assert [category["name"] for category in client.get("/api/categories").json()] == [
            "קינוחים", "ארוחות בשריות", "ארוחות קלילות", "משקאות"
        ]

    assert [recipe["title"] for recipe in recipes] == ["בדיקה", "עוגת שוקולד עם גנאש"]
    mine, sample = recipes
    assert mine["notes"] == ["הערה"]
    assert mine["sources"] == [{"kind": "manual", "url": None, "creators": [{"name": "me", "username": None}]}]
    assert mine["updated_at"] == "2026-10-20T06:15:00Z"
    assert sample["ingredient_groups"][0]["ingredients"][0]["text"] == "200 גרם שוקולד מריר"
    assert sample["is_sample"] and not mine["is_sample"]
    # The new fields: existing recipes are saved recipes with nothing to review and no imported original.
    assert all(recipe["status"] == "saved" and recipe["issues"] == [] and recipe["original"] is None for recipe in recipes)

    backups = list(data_dir.glob(f"recipes.backup-*-before-{head_revision()}.db"))
    assert len(backups) == 1
    assert table_definitions(backups[0]) == milestone3_definitions()  # the copy is from before the upgrade
    with closing(sqlite3.connect(backups[0])) as copy:
        assert copy.execute("SELECT title FROM recipes ORDER BY id").fetchall() == [("עוגת שוקולד עם גנאש",), ("בדיקה",)]


def test_starting_again_neither_migrates_nor_backs_up_again(data_dir):
    make_milestone3_database(data_dir / "recipes.db")
    with TestClient(app, base_url="http://localhost"):
        pass
    with TestClient(app, base_url="http://localhost") as client:
        assert len(client.get("/api/recipes").json()) == 2
    assert len(list(data_dir.glob("recipes.backup-*.db"))) == 1


def test_a_failed_upgrade_leaves_the_database_exactly_as_it_was(tmp_path):
    path = tmp_path / "recipes.db"
    make_milestone3_database(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("INSERT INTO recipe_sources VALUES (2, 999, 0, 'text', NULL, '[]')")  # points at no recipe
        db.commit()
    before = table_definitions(path)

    with pytest.raises(RuntimeError, match="point at missing rows"):
        upgrade_database(path)

    # The whole upgrade ran in one transaction and was rolled back: no new column, no version table.
    assert table_definitions(path) == before
    with closing(sqlite3.connect(path)) as db:
        tables = {name for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert "alembic_version" not in tables and "recipe_imports" not in tables
        assert db.execute("SELECT count(*) FROM recipes").fetchone() == (2,)
    assert len(list(tmp_path.glob("recipes.backup-*.db"))) == 1  # and the copy was made first


def test_downgrade_and_upgrade_again_keep_the_recipes(tmp_path):
    path = tmp_path / "recipes.db"
    make_milestone3_database(path)
    upgrade_database(path)
    engine = migration_engine(path)
    with engine.begin() as connection:
        command.downgrade(alembic_config(connection), "0001")
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), "head")
    engine.dispose()
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT id, title, status, issues FROM recipes ORDER BY id").fetchall() == [
            (1, "עוגת שוקולד עם גנאש", "saved", "[]"),
            (2, "בדיקה", "saved", "[]"),
        ]


def test_the_database_refuses_an_unknown_status(tmp_path):
    path = tmp_path / "recipes.db"
    make_milestone3_database(path)
    upgrade_database(path)
    with closing(sqlite3.connect(path)) as db, pytest.raises(sqlite3.IntegrityError, match="status_is_draft_or_saved"):
        db.execute("UPDATE recipes SET status = 'published' WHERE id = 1")


def test_deleting_a_recipe_deletes_its_imported_original(client, data_dir):
    with client.app.state.session_factory() as session:
        from app import crud
        from app.schemas import RecipeInput

        recipe = crud.create_import(session, RecipeInput(title="עוגה", status="draft"), original_text="עוגה\nקמח", model=None)
    assert client.delete(f"/api/recipes/{recipe.id}").status_code == 204
    with closing(sqlite3.connect(data_dir / "recipes.db")) as db:
        assert db.execute("SELECT count(*) FROM recipe_imports").fetchone() == (0,)


OLD_DESCRIPTIONS = [
    ("קינוחים", "עוגות, עוגיות, מאפים מתוקים וקינוחים"),
    ("בישולים", "מנות עיקריות ותבשילים"),
    ("ארוחות קלילות", "ארוחות קלות ומהירות, למשל פיצה מבצק יוגורט; לא בהכרח דל קלוריות"),
]


def categories_of(path: Path) -> list[tuple[str, str | None]]:
    """The top-level categories (subcategories: subcategories_of)."""
    with closing(sqlite3.connect(path)) as db:
        return db.execute("SELECT name, description FROM categories WHERE parent_id IS NULL ORDER BY id").fetchall()


def subcategories_of(path: Path) -> list[tuple[int, str, str, int]]:
    with closing(sqlite3.connect(path)) as db:
        return db.execute(
            "SELECT sub.id, parent.name, sub.name, sub.parent_id FROM categories AS sub "
            "JOIN categories AS parent ON parent.id = sub.parent_id ORDER BY sub.id"
        ).fetchall()


def test_the_starter_descriptions_are_made_clearer_but_a_description_you_changed_is_kept(tmp_path):
    path = tmp_path / "recipes.db"
    make_milestone3_database(path)
    with closing(sqlite3.connect(path)) as db:
        db.executemany("UPDATE categories SET description = ? WHERE name = ?", [(d, n) for n, d in OLD_DESCRIPTIONS])
        db.execute("UPDATE categories SET description = 'שלי' WHERE name = 'בישולים'")  # changed by you
        db.execute("INSERT INTO categories (id, name, description, parent_id) VALUES (4, 'מרקים', 'קערות חמות', NULL)")
        db.commit()
    upgrade_database(path)

    after = dict(categories_of(path))
    assert after["ארוחות בשריות"] == "שלי" and after["מרקים"] == "קערות חמות"  # yours, untouched (renamed by 0005)
    assert after["קינוחים"] == STARTER["קינוחים"] and "לא משקאות" in after["קינוחים"]
    assert after["ארוחות קלילות"] == STARTER["ארוחות קלילות"] and "על בסיס חלבי" in after["ארוחות קלילות"]
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT count(*) FROM recipes").fetchone() == (2,)


def test_the_clearer_descriptions_are_the_ones_a_new_database_starts_with_and_downgrade_restores(tmp_path):
    path = tmp_path / "recipes.db"
    make_milestone3_database(path)
    with closing(sqlite3.connect(path)) as db:
        db.executemany("UPDATE categories SET description = ? WHERE name = ?", [(d, n) for n, d in OLD_DESCRIPTIONS])
        db.commit()
    upgrade_database(path)
    assert categories_of(path) == list(STARTER.items())
    engine = migration_engine(path)
    with engine.begin() as connection:
        command.downgrade(alembic_config(connection), "0002")
    engine.dispose()
    assert categories_of(path) == OLD_DESCRIPTIONS



def test_descriptions_from_0003_take_your_meaning_and_one_you_changed_since_is_kept(tmp_path):
    path = tmp_path / "recipes.db"
    make_milestone3_database(path)
    with closing(sqlite3.connect(path)) as db:
        db.executemany("UPDATE categories SET description = ? WHERE name = ?", [(d, n) for n, d in OLD_DESCRIPTIONS])
        db.commit()
    engine = migration_engine(path)
    with engine.begin() as connection:
        command.stamp(alembic_config(connection), "0001")  # the milestone-3 tables are there already
        command.upgrade(alembic_config(connection), "0003")
    engine.dispose()
    with closing(sqlite3.connect(path)) as db:  # after 0003, you edited one description
        db.execute("UPDATE categories SET description = 'מה שאני רוצה' WHERE name = 'קינוחים'")
        db.commit()
    upgrade_database(path)
    after = dict(categories_of(path))
    assert after["קינוחים"] == "מה שאני רוצה"  # yours, untouched
    assert after["ארוחות בשריות"] == STARTER["ארוחות בשריות"] and "בשר בקר" in after["ארוחות בשריות"]
    assert after["ארוחות קלילות"] == STARTER["ארוחות קלילות"]


def database_at_0004(path: Path) -> None:
    """A milestone-3 database with the first starter descriptions, migrated up to 0004 only, with one
    recipe in "בישולים" and its imported original."""
    make_milestone3_database(path)
    with closing(sqlite3.connect(path)) as db:
        db.executemany("UPDATE categories SET description = ? WHERE name = ?", [(d, n) for n, d in OLD_DESCRIPTIONS])
        db.commit()
    engine = migration_engine(path)
    with engine.begin() as connection:
        command.stamp(alembic_config(connection), "0001")
        command.upgrade(alembic_config(connection), "0004")
    engine.dispose()
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE recipes SET category_id = 2 WHERE id = 2")
        db.execute("INSERT INTO recipe_imports VALUES (1, 2, 'text', 'בדיקה\nמערבבים.', 'qwen3:8b', '2026-10-25 10:00:00')")
        db.commit()


def rows(path: Path, table: str) -> list[tuple]:
    with closing(sqlite3.connect(path)) as db:
        return db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()


def test_0005_renames_in_place_adds_the_drinks_and_keeps_every_recipe(tmp_path):
    path = tmp_path / "recipes.db"
    database_at_0004(path)
    recipes, originals, sources = rows(path, "recipes"), rows(path, "recipe_imports"), rows(path, "recipe_sources")

    upgrade_database(path)

    with closing(sqlite3.connect(path)) as db:
        categories = db.execute("SELECT id, name, description FROM categories WHERE parent_id IS NULL ORDER BY id").fetchall()
    # Same id: the recipe that was in "בישולים" is in "ארוחות בשריות" without being touched.
    assert [(id_, name) for id_, name, _ in categories] == [
        (1, "קינוחים"), (2, "ארוחות בשריות"), (3, "ארוחות קלילות"), (4, "משקאות")
    ]
    assert [description for _, _, description in categories] == list(STARTER.values())
    # 0006 then adds two columns to the originals; their first six are untouched.
    # 0010 adds "cooked" as the last column of recipes (0 for all): every earlier column is untouched.
    assert [row[:-1] for row in rows(path, "recipes")] == recipes and [row[:6] for row in rows(path, "recipe_imports")] == originals
    # 0008 then rewrites each credit as {"name", "username"}: every other column is untouched.
    assert [row[:5] for row in rows(path, "recipe_sources")] == [row[:5] for row in sources]
    assert len(list(tmp_path.glob(f"recipes.backup-*-before-{head_revision()}.db"))) == 1


def test_0005_leaves_a_category_you_renamed_and_a_drinks_category_you_already_have(tmp_path):
    path = tmp_path / "recipes.db"
    database_at_0004(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE categories SET name = 'עיקריות' WHERE name = 'בישולים'")
        db.execute("INSERT INTO categories (name, description, parent_id) VALUES ('משקאות', 'שלי', NULL)")
        db.commit()
    upgrade_database(path)
    names = [name for name, _ in categories_of(path)]
    assert names == ["קינוחים", "עיקריות", "ארוחות קלילות", "משקאות"]
    assert dict(categories_of(path))["משקאות"] == "שלי"


def test_downgrading_0005_keeps_the_drinks_category_while_a_recipe_is_in_it(tmp_path):
    path = tmp_path / "recipes.db"
    database_at_0004(path)
    upgrade_database(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE recipes SET category_id = 4 WHERE id = 1")
        db.commit()
    engine = migration_engine(path)
    with engine.begin() as connection:
        command.downgrade(alembic_config(connection), "0004")
    engine.dispose()
    assert [name for name, _ in categories_of(path)] == ["קינוחים", "בישולים", "ארוחות קלילות", "משקאות"]
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT category_id FROM recipes ORDER BY id").fetchall() == [(4,), (2,)]


def test_0006_gives_existing_originals_no_address_and_downgrade_keeps_them(tmp_path):
    path = tmp_path / "recipes.db"
    database_at_0004(path)
    upgrade_database(path)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT kind, url, retrieved_from FROM recipe_imports").fetchall() == [("text", None, None)]
    engine = migration_engine(path)
    with engine.begin() as connection:
        command.downgrade(alembic_config(connection), "0005")
    engine.dispose()
    with closing(sqlite3.connect(path)) as db:
        assert db.execute("SELECT recipe_id, kind, original_text FROM recipe_imports").fetchall() == [(2, "text", "בדיקה\nמערבבים.")]


def test_0007_adds_the_dessert_subcategories_and_changes_no_recipe(tmp_path):
    path = tmp_path / "recipes.db"
    database_at_0004(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE recipes SET category_id = 1 WHERE id = 2")  # a dessert, no subcategory
        db.commit()
    recipes = rows(path, "recipes")
    upgrade_database(path)
    # Ids after the four top-level categories, as a new database gives them (app/seed.py).
    assert subcategories_of(path) == [(5, "קינוחים", "קינוחים רגילים", 1), (6, "קינוחים", "קינוחים בריאים", 1)]
    # The dessert stays without a subcategory until you choose one (0010 adds "cooked" last).
    assert [row[:-1] for row in rows(path, "recipes")] == recipes
    with closing(sqlite3.connect(path)) as db:
        descriptions = dict(db.execute("SELECT name, description FROM categories WHERE parent_id = 1").fetchall())
    from app.sample_data import STARTER_SUBCATEGORIES
    assert descriptions == dict(STARTER_SUBCATEGORIES["קינוחים"])


def test_0007_does_not_add_a_subcategory_you_already_have_or_without_desserts(tmp_path):
    path = tmp_path / "recipes.db"
    database_at_0004(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("INSERT INTO categories (name, description, parent_id) VALUES ('קינוחים בריאים', 'שלי', 1)")
        db.commit()
    upgrade_database(path)
    assert [(parent, name) for _, parent, name, _ in subcategories_of(path)] == [
        ("קינוחים", "קינוחים בריאים"), ("קינוחים", "קינוחים רגילים")
    ]
    other = tmp_path / "other.db"
    database_at_0004(other)
    with closing(sqlite3.connect(other)) as db:
        db.execute("UPDATE categories SET name = 'מתוקים' WHERE id = 1")  # you renamed it before 0007
        db.commit()
    upgrade_database(other)
    assert subcategories_of(other) == []


def test_downgrading_0007_keeps_a_subcategory_that_has_recipes(tmp_path):
    path = tmp_path / "recipes.db"
    database_at_0004(path)
    upgrade_database(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("UPDATE recipes SET category_id = 1, subcategory_id = 6 WHERE id = 1")
        db.commit()
    engine = migration_engine(path)
    with engine.begin() as connection:
        command.downgrade(alembic_config(connection), "0006")
    engine.dispose()
    assert [name for _, _, name, _ in subcategories_of(path)] == ["קינוחים בריאים"]


def test_a_new_database_starts_with_the_dessert_subcategories(client):
    categories = client.get("/api/categories").json()
    assert [(sub["id"], sub["name"]) for sub in categories[0]["subcategories"]] == [(5, "קינוחים רגילים"), (6, "קינוחים בריאים")]


def test_0010_leaves_every_recipe_unmarked_and_changes_nothing_else(tmp_path):
    path = tmp_path / "recipes.db"
    database_at_0004(path)
    engine = migration_engine(path)
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), "0009")
    engine.dispose()
    before = rows(path, "recipes")
    upgrade_database(path)
    after = rows(path, "recipes")
    assert [row[:-1] for row in after] == before  # the new column comes last
    assert [row[-1] for row in after] == [0] * len(before)
    engine = migration_engine(path)
    with engine.begin() as connection:
        command.downgrade(alembic_config(connection), "0009")
    engine.dispose()
    assert rows(path, "recipes") == before


def test_0011_lets_a_recipe_page_s_picture_in_and_keeps_every_attachment(tmp_path):
    path = tmp_path / "recipes.db"
    database_at_0004(path)
    engine = migration_engine(path)
    with engine.begin() as connection:
        command.upgrade(alembic_config(connection), "0010")
    engine.dispose()
    with closing(sqlite3.connect(path)) as db:
        db.execute("INSERT INTO media_files (id, sha256, path, content_type, size_bytes, created_at) VALUES (1, 'aa', 'aa/aa.jpg', 'image/jpeg', 3, '2026-10-28')")
        db.execute("INSERT INTO recipe_media (id, recipe_id, kind, status, file_id, origin, is_cover, created_at) VALUES (1, 1, 'image', 'saved', 1, 'upload', 1, '2026-10-28')")
        db.commit()
        before = rows(path, "recipe_media")
        with pytest.raises(sqlite3.IntegrityError):  # not yet
            db.execute("INSERT INTO recipe_media (recipe_id, kind, status, file_id, origin, created_at) VALUES (2, 'image', 'saved', 1, 'website', '2026-10-28')")
    upgrade_database(path)
    assert rows(path, "recipe_media") == before
    with closing(sqlite3.connect(path)) as db:
        db.execute("INSERT INTO recipe_media (recipe_id, kind, status, file_id, origin, post_url, created_at) VALUES (2, 'image', 'saved', 1, 'website', 'https://example.com/', '2026-10-28')")
        db.commit()
        with pytest.raises(sqlite3.IntegrityError):  # still one cover per recipe
            db.execute("INSERT INTO recipe_media (recipe_id, kind, status, file_id, origin, is_cover, created_at) VALUES (1, 'image', 'saved', 1, 'upload', 1, '2026-10-28')")
        with pytest.raises(sqlite3.IntegrityError):  # and only the known origins
            db.execute("INSERT INTO recipe_media (recipe_id, kind, status, file_id, origin, created_at) VALUES (2, 'image', 'saved', 1, 'elsewhere', '2026-10-28')")
    engine = migration_engine(path)
    with engine.begin() as connection:
        command.downgrade(alembic_config(connection), "0010")
    engine.dispose()
    assert rows(path, "recipe_media") == before  # the website picture's attachment went; the rest stayed


def test_0008_turns_each_credit_into_a_name_or_a_username_and_downgrade_turns_it_back(tmp_path):
    path = tmp_path / "recipes.db"
    database_at_0004(path)
    with closing(sqlite3.connect(path)) as db:
        db.execute("DELETE FROM recipe_sources")
        db.executemany(
            "INSERT INTO recipe_sources (id, recipe_id, position, kind, url, creators) VALUES (?, 2, ?, ?, NULL, ?)",
            [(1, 0, "instagram", '["ritakadosh_", "Lior Mashiach"]'), (2, 1, "website", '["Example Kitchen", "@baker"]'), (3, 2, "text", "[]")],
        )
        db.commit()
    upgrade_database(path)
    with closing(sqlite3.connect(path)) as db:
        credits = [json.loads(c) for (c,) in db.execute("SELECT creators FROM recipe_sources ORDER BY id")]
    assert credits == [
        [{"name": None, "username": "ritakadosh_"}, {"name": "Lior Mashiach", "username": None}],
        [{"name": "Example Kitchen", "username": None}, {"name": None, "username": "baker"}],
        [],
    ]
    engine = migration_engine(path)
    with engine.begin() as connection:
        command.downgrade(alembic_config(connection), "0007")
    engine.dispose()
    with closing(sqlite3.connect(path)) as db:
        credits = [json.loads(c) for (c,) in db.execute("SELECT creators FROM recipe_sources ORDER BY id")]
    assert credits == [["ritakadosh_", "Lior Mashiach"], ["Example Kitchen", "@baker"], []]
