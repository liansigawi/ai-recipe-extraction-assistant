"""A draft from a recipe page's own Schema.org data (app/importers/website.py): its words exactly as the
page gives them. No model writes any of it; a model is asked only for the category, by the same rules
as every import (only an existing category, or none)."""

from app import schemas
from app.extraction.output import Classification
from app.extraction.quantity import find_quantity
from app.extraction.review import content_points, resolve_classification
from app.importers.website import StructuredRecipe


def structured_draft(
    recipe: StructuredRecipe,
    source_text: str,
    categories: list[schemas.Category],
    classification: Classification | None,
    unclassified_because: str | None = None,
) -> schemas.RecipeInput:
    """The draft: title, ingredient lines in their groups (each with the amount it writes, as for any
    import), steps in their sections, servings, and the page's times as one note. Without a classification: unclassified,
    with `unclassified_because` as the review point (None: no point, e.g. before the model is asked)."""
    issues: list[schemas.Issue] = []
    title = recipe.title.strip()
    if not title:
        title = "מתכון מהאתר"
        issues.append(schemas.Issue(kind="missing_title", message='בנתוני המתכון שבדף אין שם. הכותרת "מתכון מהאתר" זמנית; שנו אותה.'))
    ingredient_groups = [
        schemas.IngredientGroup(name=name, ingredients=[schemas.Ingredient(text=line, quantity=find_quantity(line)) for line in lines])
        for name, lines in recipe.ingredient_groups
        if lines
    ]
    groups = [schemas.StepGroup(name=name, steps=steps) for name, steps in recipe.step_groups if steps]
    if not ingredient_groups:
        issues.append(schemas.Issue(kind="missing_information", message="בנתוני המתכון שבדף אין רשימת מצרכים. העתיקו אותם מהדף אם צריך."))
    if not groups:
        issues.append(schemas.Issue(kind="missing_information", message="בנתוני המתכון שבדף אין שלבי הכנה. העתיקו אותם מהדף אם צריך."))
    issues.extend(content_points(recipe.ingredients, recipe.steps, source_text))
    category_id = subcategory_id = None
    if classification is not None:
        category_id, subcategory_id, issue = resolve_classification(classification, categories)
        if issue is not None:
            issues.append(issue)
    elif unclassified_because is not None:
        issues.append(schemas.Issue(kind="classification_unresolved", message=unclassified_because))
    times = " · ".join(f"{label}: {value}" for label, value in recipe.times.items())
    return schemas.RecipeInput(
        title=title,
        servings=recipe.servings,
        ingredient_groups=ingredient_groups,
        step_groups=groups,
        notes=[times] if times else [],
        sources=[schemas.Source(kind="website")],
        category_id=category_id,
        subcategory_id=subcategory_id,
        status="draft",
        issues=issues,
    )
