-- The tables exactly as milestone 3 created them (Base.metadata.create_all, commit c7d2eee).
-- Databases from milestone 3 are recognized and stamped as migration 0001; tests check that
-- migration 0001 creates this same schema.

CREATE TABLE categories (
	id INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	description VARCHAR, 
	parent_id INTEGER, 
	PRIMARY KEY (id), 
	UNIQUE (id, parent_id), 
	FOREIGN KEY(parent_id) REFERENCES categories (id)
);

CREATE TABLE recipe_sources (
	id INTEGER NOT NULL, 
	recipe_id INTEGER NOT NULL, 
	position INTEGER NOT NULL, 
	kind VARCHAR NOT NULL, 
	url VARCHAR, 
	creators JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(recipe_id) REFERENCES recipes (id) ON DELETE CASCADE
);

CREATE TABLE recipes (
	id INTEGER NOT NULL, 
	title VARCHAR NOT NULL, 
	category_id INTEGER, 
	subcategory_id INTEGER, 
	servings VARCHAR, 
	ingredient_groups JSON NOT NULL, 
	step_groups JSON NOT NULL, 
	notes JSON NOT NULL, 
	is_sample BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(subcategory_id, category_id) REFERENCES categories (id, parent_id), 
	CONSTRAINT subcategory_needs_category CHECK (subcategory_id IS NULL OR category_id IS NOT NULL), 
	FOREIGN KEY(category_id) REFERENCES categories (id)
);
