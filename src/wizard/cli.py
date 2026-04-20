"""Click-based CLI entry points for the MTG wizard."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from wizard.collection import parse_manabox_csv
from wizard.config import Settings, load_settings
from wizard.database import count_collection, get_collection, init_db, insert_collection
from wizard.errors import WizardAPIError
from wizard.exporter import render_deck, write_deck
from wizard.models import CollectionCard, DeckSuggestion
from wizard.scorer import rank_collection_for_format
from wizard.scryfall import download_bulk_data, enrich_collection

_console = Console()


# --- Internals -------------------------------------------------------------

def _require_api_key(settings: Settings) -> str:
    """Return the Anthropic API key or exit with a clear error message."""
    if not settings.anthropic_api_key:
        _console.print(
            "[red]ANTHROPIC_API_KEY is not set.[/red] "
            "Copy .env.example to .env and add your key."
        )
        raise SystemExit(1)
    return settings.anthropic_api_key


def _render_deck_panel(deck: DeckSuggestion) -> None:
    """Pretty-print a DeckSuggestion using Rich panels and tables."""
    header = f"[bold cyan]{deck.deck_name}[/] · {deck.format}"
    if deck.commander:
        header += f" · Commander: [yellow]{deck.commander}[/]"
    _console.print(Panel(header, border_style="cyan"))

    main_table = Table(title="Mainboard", show_edge=True, header_style="bold")
    main_table.add_column("Qty", justify="right", width=4)
    main_table.add_column("Name")
    main_table.add_column("Set", width=6)
    main_table.add_column("CN", width=6)
    total_main = 0
    for card in deck.mainboard:
        total_main += card.quantity
        main_table.add_row(
            str(card.quantity),
            card.name,
            (card.set_code or "").upper(),
            card.collector_number or "",
        )
    main_table.caption = f"{total_main} cards"
    _console.print(main_table)

    if deck.sideboard:
        side_table = Table(title="Sideboard", show_edge=True, header_style="bold")
        side_table.add_column("Qty", justify="right", width=4)
        side_table.add_column("Name")
        total_side = 0
        for card in deck.sideboard:
            total_side += card.quantity
            side_table.add_row(str(card.quantity), card.name)
        side_table.caption = f"{total_side} cards"
        _console.print(side_table)

    _console.print(
        Panel(deck.strategy or "(no strategy notes)", title="Strategy", border_style="magenta")
    )
    if deck.key_synergies:
        _console.print(
            Panel(
                "\n".join(f"- {s}" for s in deck.key_synergies),
                title="Key synergies",
                border_style="green",
            )
        )


# --- Click group -----------------------------------------------------------

@click.group()
@click.pass_context
def main(ctx: click.Context) -> None:
    """MTG Wizard — build decks from your ManaBox collection with Claude AI."""
    ctx.ensure_object(dict)
    ctx.obj["settings"] = load_settings()


@main.command("sync")
@click.option("--force", is_flag=True, help="Force a full re-download even if cache is fresh.")
@click.pass_context
def sync(ctx: click.Context, force: bool) -> None:
    """Download or refresh the Scryfall oracle_cards bulk data."""
    settings: Settings = ctx.obj["settings"]
    _console.print(f"Syncing Scryfall data into [cyan]{settings.db_path}[/]...")
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=_console,
        transient=True,
    ) as progress:
        task = progress.add_task("Downloading oracle_cards bulk data...", total=None)
        try:
            written = download_bulk_data(settings.db_path, force=force)
        except Exception as exc:  # noqa: BLE001 — surface any error to the user.
            progress.remove_task(task)
            _console.print(f"[red]Sync failed:[/] {exc}")
            raise SystemExit(1) from exc
        progress.remove_task(task)
    _console.print(f"[green]Sync complete.[/] Cards in cache: [bold]{written}[/]")


@main.command("import-collection")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--mode",
    type=click.Choice(["replace", "append"], case_sensitive=False),
    default="replace",
    show_default=True,
    help="`replace` wipes the existing collection first; `append` keeps it.",
)
@click.option(
    "--yes",
    is_flag=True,
    help="Skip the 'replace existing cards?' confirmation prompt.",
)
@click.pass_context
def import_collection(
    ctx: click.Context,
    path: Path,
    mode: str,
    yes: bool,
) -> None:
    """Parse and store a ManaBox CSV export in the local collection.

    By default (`--mode replace`) the existing collection is cleared first so
    re-importing the same file does not produce duplicates. Use `--mode append`
    to keep previous rows. Any non-empty existing collection triggers an
    interactive confirmation unless `--yes` is passed or stdin is not a TTY.
    """
    settings: Settings = ctx.obj["settings"]
    _console.print(f"Parsing [cyan]{path}[/]...")
    try:
        cards = parse_manabox_csv(path)
    except Exception as exc:  # noqa: BLE001
        _console.print(f"[red]Failed to parse CSV:[/] {exc}")
        raise SystemExit(1) from exc

    conn = init_db(settings.db_path)
    try:
        mode_normalized = mode.lower()
        replace = mode_normalized == "replace"
        if replace:
            existing = count_collection(conn)
            if existing > 0 and not yes:
                import sys as _sys

                if _sys.stdin.isatty():
                    answer = click.prompt(
                        f"Replace {existing} existing cards? [y/N]",
                        default="N",
                        show_default=False,
                    )
                    if answer.strip().lower() not in {"y", "yes"}:
                        _console.print("[yellow]Aborted.[/]")
                        raise SystemExit(1)
                else:
                    _console.print(
                        f"[red]Refusing to replace {existing} existing cards "
                        f"without --yes on non-interactive stdin.[/]"
                    )
                    raise SystemExit(1)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=_console,
            transient=True,
        ) as progress:
            task = progress.add_task(f"Inserting {len(cards)} cards...", total=None)
            inserted = insert_collection(conn, cards, replace=replace)
            progress.remove_task(task)
    finally:
        conn.close()
    verb = "Replaced with" if mode_normalized == "replace" else "Appended"
    _console.print(f"[green]{verb} {inserted} cards.[/]")


@main.command("collection")
@click.pass_context
def collection(ctx: click.Context) -> None:
    """Show collection statistics."""
    settings: Settings = ctx.obj["settings"]
    conn = init_db(settings.db_path)
    try:
        rows = get_collection(conn)
    finally:
        conn.close()

    total_qty = sum(int(r.get("quantity") or 0) for r in rows)
    unique = len(rows)
    sets = sorted({(r.get("set_code") or "").upper() for r in rows if r.get("set_code")})

    table = Table(title="Collection", header_style="bold")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Unique rows", str(unique))
    table.add_row("Total copies", str(total_qty))
    table.add_row("Sets represented", str(len(sets)))
    _console.print(table)
    if sets:
        _console.print(
            Panel(
                ", ".join(sets[:50]) + (" ..." if len(sets) > 50 else ""),
                title="Sets",
            )
        )


@main.command("build")
@click.option(
    "--format",
    "format_name",
    type=click.Choice(
        ["Commander", "Standard", "Modern", "Pioneer", "Legacy", "Pauper"],
        case_sensitive=False,
    ),
    prompt="Format",
    help="MTG format for the suggested deck.",
)
@click.option(
    "--colors",
    default="",
    help='Color identity string, e.g. "WUB" or "WUBRG". Blank = any.',
)
@click.option(
    "--commander",
    default="",
    help="Preferred commander name (Commander format only).",
)
@click.option(
    "--output",
    "output_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the deck as ManaBox-importable text to this .txt path.",
)
@click.pass_context
def build(
    ctx: click.Context,
    format_name: str,
    colors: str,
    commander: str,
    output_path: Path | None,
) -> None:
    """Run the Wizard AI to suggest a deck from your imported collection."""
    # Imported lazily so `sync`, `import-collection`, and `collection` work offline.
    import anthropic

    settings: Settings = ctx.obj["settings"]
    api_key = _require_api_key(settings)

    # Accept either contiguous ("WUB") or comma-separated ("W,U,B") color inputs.
    if "," in colors:
        color_identity: list[str] | None = [
            c.strip().upper() for c in colors.split(",") if c.strip()
        ] or None
    else:
        color_identity = [ch.upper() for ch in colors if ch.strip()] or None

    conn = init_db(settings.db_path)
    try:
        rows = get_collection(conn)
        if not rows:
            _console.print(
                "[yellow]Your collection is empty.[/] Run "
                "[cyan]wizard import-collection <path>[/] first."
            )
            raise SystemExit(1)

        coll = [
            CollectionCard(
                name=str(r.get("name") or ""),
                set_code=str(r.get("set_code") or ""),
                set_name="",
                collector_number=str(r.get("collector_number") or ""),
                foil=bool(r.get("foil") or 0),
                rarity="",
                quantity=int(r.get("quantity") or 1),
                manabox_id="",
                scryfall_id=str(r.get("scryfall_id") or ""),
                purchase_price=None,
                misprint=False,
                altered=False,
                condition=str(r.get("condition") or ""),
                language=str(r.get("language") or ""),
                currency="",
            )
            for r in rows
        ]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=_console,
            transient=True,
        ) as progress:
            task = progress.add_task("Enriching collection with Scryfall data...", total=None)
            enriched_pairs = enrich_collection(conn, coll)
            progress.remove_task(task)

        enriched = [(c, sc) for c, sc in enriched_pairs if sc is not None]
        if not enriched:
            _console.print(
                "[yellow]No cards matched Scryfall data.[/] "
                "Run [cyan]wizard sync[/] first."
            )
            raise SystemExit(1)

        ranked = rank_collection_for_format(enriched, format_name, color_identity)
        if not ranked:
            _console.print(
                f"[yellow]No legal cards in {format_name} for the selected colors.[/]"
            )
            raise SystemExit(1)

        _console.print(
            f"Asking the Wizard to build a [cyan]{format_name}[/] deck "
            f"from {len(ranked)} eligible cards..."
        )
        # `max_retries=3` lets the SDK handle transient 429s / 5xx internally
        # before any exception reaches our classifier in deckbuilder.
        client = anthropic.Anthropic(api_key=api_key, max_retries=3)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=_console,
            transient=True,
        ) as progress:
            task = progress.add_task("Consulting the Wizard...", total=None)
            try:
                # Lazy import keeps `anthropic` out of the offline command paths.
                from wizard.deckbuilder import suggest_deck

                try:
                    deck = suggest_deck(
                        client=client,
                        format_name=format_name,
                        ranked_cards=ranked,
                        color_identity=color_identity,
                        model=settings.model,
                    )
                except WizardAPIError as exc:
                    # `finally` below tears down the progress task; just
                    # convert the user-facing message and exit cleanly.
                    _console.print(f"[red]{exc.user_message}[/]")
                    raise SystemExit(1) from exc
            finally:
                progress.remove_task(task)
    finally:
        conn.close()

    # If the user asked for Commander but the deck was returned without one,
    # fall back to the --commander hint so the exporter renders a Commander line.
    if format_name.lower() == "commander" and not deck.commander and commander:
        deck.commander = commander

    _render_deck_panel(deck)
    if output_path:
        write_deck(deck, output_path)
        _console.print(f"[green]Deck exported to[/] [cyan]{output_path}[/]")
    else:
        # Always print the ManaBox text block so the user can copy/paste it.
        _console.print(Panel(render_deck(deck), title="ManaBox text", border_style="blue"))


if __name__ == "__main__":  # pragma: no cover
    main(obj={})
