from rich.console import Console
from rich.panel import Panel

console = Console()

def banner(title: str, subtitle: str | None = None) -> None:
    text = title if subtitle is None else f"{title}\n{subtitle}"
    console.print(Panel.fit(text, border_style="cyan"))
