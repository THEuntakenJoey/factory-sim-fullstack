class Recipe:
    def __init__(self, steps: list):
        # e.g. ["DEPOSIT", "ETCH", "MEASURE"]
        self.steps = steps

class Content:
    def __init__(self, content_id: str, recipe: Recipe):
        self.id = content_id
        self.recipe = recipe
        self.step_idx = 0

    def get_next_machine_type(self):
        if self.step_idx < len(self.recipe.steps):
            return self.recipe.steps[self.step_idx]
        return None

    def complete_step(self):
        self.step_idx += 1
