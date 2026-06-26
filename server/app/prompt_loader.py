from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from string import Template


PROMPTS_DIR = Path(__file__).with_name("prompts")


@dataclass(frozen=True)
class PromptPair:
    system: str
    user: str


@lru_cache(maxsize=128)
def _load_prompt_template(provider: str, task: str, part: str) -> Template:
    path = PROMPTS_DIR / provider / f"{task}.{part}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Missing prompt template: {path}")
    return Template(path.read_text(encoding="utf-8").strip())


def render_prompt(provider: str, task: str, **values: object) -> PromptPair:
    variables = {key: str(value) for key, value in values.items()}
    return PromptPair(
        system=_load_prompt_template(provider, task, "system").safe_substitute(variables),
        user=_load_prompt_template(provider, task, "user").safe_substitute(variables),
    )
