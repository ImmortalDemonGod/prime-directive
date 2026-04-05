import asyncio
import difflib
import json
import logging
import os
import shutil
import sys
from click.core import ParameterSource
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, cast

import httpx
import typer
import yaml
from dotenv import load_dotenv

# Hydra imports
from hydra import compose, initialize_config_dir
from hydra.core.global_hydra import GlobalHydra
from omegaconf import DictConfig, OmegaConf
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlalchemy import select

# Core imports
from prime_directive.core.config import register_configs
from prime_directive.core.db import (
    ContextSnapshot,
    EventLog,
    EventType,
    dispose_engine,
    get_session,
    init_db,
)
from prime_directive.core.dependencies import (
    get_ollama_status,
    has_openai_api_key,
)
from prime_directive.core.dossier_ai import generate_theme_suggestions_with_ai
from prime_directive.core.empire import load_empire_if_exists
from prime_directive.core.git_utils import GitStatus, get_status
from prime_directive.core.identity import (
    apply_operator_dossier_tag_normalization_fixes,
    default_operator_dossier,
    get_dossier_path,
    load_operator_dossier,
    operator_dossier_to_dict,
    preview_operator_dossier_tag_normalization_fixes,
    sync_connection_surface,
    validate_operator_dossier_file,
    write_operator_dossier,
)
from prime_directive.core.logging_utils import setup_logging
from prime_directive.core.orchestrator import run_switch
from prime_directive.core.scribe import generate_sitrep
from prime_directive.core.skill_scanner import (
    apply_sync_proposals,
    build_sync_proposals,
)
from prime_directive.core.tasks import get_active_task
from prime_directive.core.terminal import capture_terminal_state
from prime_directive.core.tmux import ensure_session
from prime_directive.core.windsurf import launch_editor

# Load .env from multiple locations (in order of priority)
# 1. Current working directory
# 2. User's home ~/.prime-directive/.env
# 3. The prime-directive repo root
load_dotenv()  # CWD
load_dotenv(Path.home() / ".prime-directive" / ".env")
load_dotenv(Path(__file__).parent.parent.parent / ".env")

app = typer.Typer()
dossier_app = typer.Typer()
# Export cli for entry point
cli = app
console = Console()
logger = logging.getLogger("prime_directive")

_EXIT_CODE_SHELL_ATTACH = 88

app.add_typer(dossier_app, name="dossier")
empire_app = typer.Typer()
app.add_typer(empire_app, name="empire")


def _normalize_repo_id(repo_id: str) -> str:
    """
    Normalize a repository identifier by trimming surrounding whitespace and removing any trailing forward or backward slashes.
    
    Parameters:
        repo_id (str): The repository identifier to normalize.
    
    Returns:
        str: The normalized repository identifier.
    """
    return repo_id.strip().rstrip("/\\")


def _resolve_repo_id(repo_id: str, cfg: DictConfig) -> str:
    candidate = _normalize_repo_id(repo_id)
    if candidate in cfg.repos:
        return candidate

    matches = difflib.get_close_matches(
        candidate,
        list(cfg.repos.keys()),
        n=1,
        cutoff=0.6,
    )
    msg = f"Repository '{repo_id}' not found in configuration."
    if matches:
        msg = f"{msg} Did you mean '{matches[0]}'?"
    console.print(f"[bold red]Error:[/bold red] {msg}")
    logger.error(msg)
    raise typer.Exit(code=1)


def load_config() -> DictConfig:
    """
    Compose and return the application's Hydra configuration.
    
    Merges the packaged config with an optional user config at ~/.prime-directive/config.yaml when present, and expands variables/user home in cfg.system.db_path, cfg.system.log_path, and each repo.path when possible. On failure prints an error, logs it, and exits the process with status code 1.
    
    Returns:
        DictConfig: The composed Hydra configuration.
    """
    # Ensure any previous Hydra instance is cleared
    GlobalHydra.instance().clear()

    # Register structured configs
    register_configs()

    # Compute absolute path to conf directory relative to this file
    # pd.py is in prime_directive/bin/, conf is in prime_directive/conf/
    conf_dir = Path(__file__).parent.parent / "conf"
    conf_path = str(conf_dir.resolve())

    try:
        with initialize_config_dir(version_base=None, config_dir=conf_path):
            cfg = compose(config_name="config")
        OmegaConf.set_struct(cfg, False)

        user_cfg_path = Path.home() / ".prime-directive" / "config.yaml"
        if user_cfg_path.exists():
            user_cfg = OmegaConf.load(str(user_cfg_path))
            cfg = cast(DictConfig, OmegaConf.merge(cfg, user_cfg))

        try:
            cfg.system.db_path = os.path.expanduser(
                os.path.expandvars(str(cfg.system.db_path))
            )
            cfg.system.log_path = os.path.expanduser(
                os.path.expandvars(str(cfg.system.log_path))
            )
        except Exception:
            pass

        try:
            for _rid, repo in cfg.repos.items():
                repo.path = os.path.expanduser(
                    os.path.expandvars(str(repo.path))
                )
        except Exception:
            pass

        return cfg
    except Exception as e:
        msg = f"Error loading config: {e}"
        console.print(f"[bold red]{msg}[/bold red]")
        logger.critical(msg)
        sys.exit(1)


async def _load_recent_snapshot_texts(
    db_path: str,
    limit: int = 100,
) -> tuple[list[str], int, int]:
    """
    Collect recent human-authored snapshot texts from the database for the past 30 days.
    
    Only snapshots whose timestamp is within the last 30 days are considered. The function returns up to `limit` snapshots, extracting non-empty text from the snapshot fields `human_objective`, `human_blocker`, `human_next_step`, and `human_note`.
    
    Parameters:
        db_path (str): Path to the SQLite/database file used by the application.
        limit (int): Maximum number of snapshots to fetch (default 100).
    
    Returns:
        tuple[list[str], int, int]:
            - list[str]: Collected non-empty snapshot texts (trimmed), in newest-first order as retrieved.
            - int: Number of snapshot records fetched from the database (<= `limit`).
            - int: Number of distinct `repo_id` values represented among the fetched snapshots.
    """
    await init_db(db_path)
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    try:
        async for session in get_session(db_path):
            timestamp_col = cast(Any, ContextSnapshot.timestamp)
            stmt = (
                select(ContextSnapshot)
                .where(timestamp_col >= cutoff)
                .order_by(timestamp_col.desc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            snapshots = list(result.scalars().all())
            texts: list[str] = []
            repo_ids: set[str] = set()
            for snapshot in snapshots:
                repo_ids.add(snapshot.repo_id)
                for value in [
                    snapshot.human_objective,
                    snapshot.human_blocker,
                    snapshot.human_next_step,
                    snapshot.human_note,
                ]:
                    if value and value.strip():
                        texts.append(value)
            return texts, len(snapshots), len(repo_ids)
    finally:
        await dispose_engine()
    return [], 0, 0


def _seed_programming_languages(dossier: Any, summaries: list[Any]) -> None:
    """
    Ensure the dossier's programming languages list includes any recognized languages found in the provided summaries.
    
    Reads existing non-empty entries from dossier.identity.languages["programming"], adds any of the recognized languages {"Python", "JavaScript", "TypeScript", "Rust", "Go", "SQL"} found in each summary.detected_skills, and writes back a sorted, deduplicated list to dossier.identity.languages["programming"].
    
    Parameters:
        dossier (Any): Operator dossier object with an attribute `identity.languages` (a mapping where the `"programming"` key holds a list of language names).
        summaries (list[Any]): Iterable of summary objects, each exposing `detected_skills` (an iterable of skill/language names).
    """
    detected_languages = {
        item
        for item in dossier.identity.languages.get("programming", [])
        if str(item).strip()
    }
    for summary in summaries:
        for skill_name in summary.detected_skills:
            if skill_name in {
                "Python",
                "JavaScript",
                "TypeScript",
                "Rust",
                "Go",
                "SQL",
            }:
                detected_languages.add(skill_name)
    dossier.identity.languages["programming"] = sorted(detected_languages)


def _bootstrap_dossier(cfg: DictConfig) -> tuple[Any, list[Any], list[Any]]:
    """
    Create and initialize an operator dossier by generating sync proposals from the provided configuration and applying them.
    
    Parameters:
        cfg (DictConfig): Composed application configuration used to discover configured repositories and proposal settings.
    
    Returns:
        tuple: (dossier, summaries, proposals)
            dossier: The initialized operator dossier object with applied proposals and synchronized connection surface.
            summaries: List of repository scan summaries used to infer proposals and programming languages.
            proposals: List of sync proposals that were generated and applied to the dossier.
    """
    dossier = default_operator_dossier()
    summaries, proposals = build_sync_proposals(cfg, dossier)
    apply_sync_proposals(dossier, proposals)
    _seed_programming_languages(dossier, summaries)
    sync_connection_surface(dossier)
    return dossier, summaries, proposals


def _render_connection_surface_table(
    surface: dict[str, list[str]],
) -> tuple[Table, int]:
    """
    Render a Rich table summarizing connection-surface tag categories and count the total tags.
    
    Parameters:
        surface (dict[str, list[str]]): Mapping from connection-surface category keys
            (e.g., "experience_tags", "topic_tags", "geographic_tags",
            "education_tags", "industry_tags", "hobby_tags", "philosophy_tags")
            to lists of tag strings.
    
    Returns:
        tuple[Table, int]: A tuple containing the rendered Rich Table and the total
        number of tags across all categories.
    """
    table = Table(show_header=False)
    table.add_column("Category", style="bold cyan")
    table.add_column("Tags")
    total_tags = 0
    for key, label in [
        ("experience_tags", "Experience"),
        ("topic_tags", "Topics"),
        ("geographic_tags", "Geography"),
        ("education_tags", "Education"),
        ("industry_tags", "Industries"),
        ("hobby_tags", "Hobbies"),
        ("philosophy_tags", "Philosophy"),
    ]:
        values = surface.get(key, [])
        total_tags += len(values)
        table.add_row(label, ", ".join(values) or "-")
    return table, total_tags


def _format_skill_profile(depth: str, recency: str) -> str:
    """
    Format a compact skill profile showing a proficiency bar, the depth label, and recency.
    
    Parameters:
        depth (str): Proficiency level; expected values include "expert", "proficient", "familiar". If unknown or empty, a placeholder bar and `-` label are used.
        recency (str): Human-readable recency string (e.g., "recent", "6 months ago"); if empty, `-` is used.
    
    Returns:
        str: A single-line formatted profile like "███████████ expert (recent)" where the bar corresponds to `depth`, followed by the depth label and recency in parentheses.
    """
    bars = {
        "expert": "███████████",
        "proficient": "████████░░░",
        "familiar": "████░░░░░░░",
    }
    return (
        f"{bars.get(depth, '░░░░░░░░░░░')} {depth or '-'} ({recency or '-'})"
    )


def _print_capabilities_layer(dossier: Any) -> None:
    """
    Prints Layer 2 (Technical Capabilities) of an operator dossier to the console.
    
    Displays four sections with counts and tables (or "-" when empty):
    - Skills: rows with Skill, Profile, and Evidence.
    - Domain expertise: comma-separated list of domain tags.
    - Projects built: rows with Project, Tech Stack, Capability Tags, and Description.
    - Methodologies: rows with Methodology, Description, and Contexts.
    
    Parameters:
        dossier (Any): Operator dossier object expected to expose
            `capabilities.skills`, `capabilities.domain_expertise`,
            `capabilities.projects_built`, and `capabilities.methodologies`.
    """
    console.print(
        "[bold]Operator Dossier — Layer 2: Technical Capabilities[/bold]"
    )

    console.rule(f"Skills ({len(dossier.capabilities.skills)})")
    if dossier.capabilities.skills:
        skill_table = Table()
        skill_table.add_column("Skill")
        skill_table.add_column("Profile")
        skill_table.add_column("Evidence")
        for skill in dossier.capabilities.skills:
            skill_table.add_row(
                skill.name or "-",
                _format_skill_profile(skill.depth, skill.recency),
                skill.evidence or "-",
            )
        console.print(skill_table)
    else:
        console.print("-")

    console.rule(
        f"Domain Expertise ({len(dossier.capabilities.domain_expertise)})"
    )
    console.print(", ".join(dossier.capabilities.domain_expertise) or "-")

    console.rule(
        f"Projects Built ({len(dossier.capabilities.projects_built)})"
    )
    if dossier.capabilities.projects_built:
        project_table = Table()
        project_table.add_column("Project")
        project_table.add_column("Tech Stack")
        project_table.add_column("Capability Tags")
        project_table.add_column("Description")
        for project in dossier.capabilities.projects_built:
            project_table.add_row(
                project.name or "-",
                ", ".join(project.tech_stack) or "-",
                ", ".join(project.capability_tags) or "-",
                project.description or "-",
            )
        console.print(project_table)
    else:
        console.print("-")

    console.rule(f"Methodologies ({len(dossier.capabilities.methodologies)})")
    if dossier.capabilities.methodologies:
        methodology_table = Table()
        methodology_table.add_column("Methodology")
        methodology_table.add_column("Description")
        methodology_table.add_column("Contexts")
        for methodology in dossier.capabilities.methodologies:
            methodology_table.add_row(
                methodology.name or "-",
                methodology.description or "-",
                ", ".join(methodology.applicable_contexts) or "-",
            )
        console.print(methodology_table)
    else:
        console.print("-")


def _print_identity_layer(dossier: Any) -> None:
    """
    Print Layer 1 (Human Identity) of an operator dossier to the console.
    
    Prints the dossier's education entries, spoken and programming languages, hobbies, formative experiences,
    intellectual influences, and values as formatted Rich console sections and tables.
    
    Parameters:
        dossier (Any): Operator dossier object whose `identity` attribute provides:
            - `education`: iterable of records with `institution`, `degree`, `field`, `years`
            - `languages`: dict with `spoken` and `programming` lists
            - `hobbies`: iterable of hobby strings
            - `formative_experiences`: iterable of strings
            - `intellectual_influences`: iterable of strings
            - `values`: iterable of strings
    
    """
    console.print("[bold]Operator Dossier — Layer 1: Human Identity[/bold]")

    console.rule(f"Education ({len(dossier.identity.education)})")
    if dossier.identity.education:
        table = Table()
        table.add_column("Institution")
        table.add_column("Degree")
        table.add_column("Field")
        table.add_column("Years")
        for item in dossier.identity.education:
            table.add_row(
                item.institution or "-",
                item.degree or "-",
                item.field or "-",
                item.years or "-",
            )
        console.print(table)
    else:
        console.print("-")

    console.rule("Languages")
    spoken = ", ".join(dossier.identity.languages.get("spoken", [])) or "-"
    programming = (
        ", ".join(dossier.identity.languages.get("programming", [])) or "-"
    )
    console.print(f"Spoken: {spoken}")
    console.print(f"Programming: {programming}")

    console.rule(f"Hobbies ({len(dossier.identity.hobbies)})")
    console.print(", ".join(dossier.identity.hobbies) or "-")

    console.rule(
        f"Formative Experiences ({len(dossier.identity.formative_experiences)})"
    )
    console.print("\n".join(dossier.identity.formative_experiences) or "-")

    console.rule(
        f"Intellectual Influences ({len(dossier.identity.intellectual_influences)})"
    )
    console.print("\n".join(dossier.identity.intellectual_influences) or "-")

    console.rule(f"Values ({len(dossier.identity.values)})")
    console.print("\n".join(dossier.identity.values) or "-")


def _print_network_layer(dossier: Any) -> None:
    """
    Render Layer 3 ("Professional Network") of the operator dossier to the console.
    
    Prints a header and three sections:
    - Companies: a table of company name, role, years, and accomplishment (prints `-` for missing values or when the list is empty).
    - Industries: a comma-separated list of industries (or `-` when empty).
    - Institutional Overlaps: newline entries formatted as `type: value` (or `-` when empty).
    
    Parameters:
        dossier (Any): Operator dossier object containing `network.companies`, `network.industries`, and `network.institutional_overlaps`.
    """
    console.print(
        "[bold]Operator Dossier — Layer 3: Professional Network[/bold]"
    )

    console.rule(f"Companies ({len(dossier.network.companies)})")
    if dossier.network.companies:
        table = Table()
        table.add_column("Company")
        table.add_column("Role")
        table.add_column("Years")
        table.add_column("Accomplishment")
        for item in dossier.network.companies:
            table.add_row(
                item.name or "-",
                item.role or "-",
                item.years or "-",
                item.accomplishment or "-",
            )
        console.print(table)
    else:
        console.print("-")

    console.rule(f"Industries ({len(dossier.network.industries)})")
    console.print(", ".join(dossier.network.industries) or "-")

    console.rule(
        f"Institutional Overlaps ({len(dossier.network.institutional_overlaps)})"
    )
    if dossier.network.institutional_overlaps:
        for item in dossier.network.institutional_overlaps:
            console.print(f"{item.get('type', '-')}: {item.get('value', '-')}")
    else:
        console.print("-")


def _print_positioning_layer(dossier: Any) -> None:
    """
    Render Layer 4 ("Strategic Positioning") of an operator dossier to the console.
    
    Prints the positioning statement, competitive differentiation list, an offerings table (name, description, deliverable, timeline), case studies (title/client and outcome/description), and the revenue model. Empty or missing sections are rendered as "-".
    
    Parameters:
        dossier (Any): Operator dossier object with a `positioning` attribute exposing:
            - `positioning_statement` (str)
            - `competitive_differentiation` (list[str])
            - `offerings` (iterable of objects with `name`, `description`, `deliverable`, `typical_timeline`)
            - `case_studies` (list[dict], where each dict may contain `title`, `client`, `outcome`, `description`)
            - `revenue_model` (str)
    """
    console.print(
        "[bold]Operator Dossier — Layer 4: Strategic Positioning[/bold]"
    )

    console.rule("Positioning Statement")
    console.print(dossier.positioning.positioning_statement or "-")

    console.rule(
        f"Competitive Differentiation ({len(dossier.positioning.competitive_differentiation)})"
    )
    console.print(
        "\n".join(dossier.positioning.competitive_differentiation) or "-"
    )

    console.rule(f"Offerings ({len(dossier.positioning.offerings)})")
    if dossier.positioning.offerings:
        table = Table()
        table.add_column("Name")
        table.add_column("Description")
        table.add_column("Deliverable")
        table.add_column("Timeline")
        for item in dossier.positioning.offerings:
            table.add_row(
                item.name or "-",
                item.description or "-",
                item.deliverable or "-",
                item.typical_timeline or "-",
            )
        console.print(table)
    else:
        console.print("-")

    console.rule(f"Case Studies ({len(dossier.positioning.case_studies)})")
    if dossier.positioning.case_studies:
        for item in dossier.positioning.case_studies:
            title = item.get("title") or item.get("client") or "Case Study"
            outcome = item.get("outcome") or item.get("description") or "-"
            console.print(f"{title}: {outcome}")
    else:
        console.print("-")

    console.rule("Revenue Model")
    console.print(dossier.positioning.revenue_model or "-")


def _print_connection_surface_layer(dossier: Any) -> None:
    """
    Prints Layer 5 (Operator Connection Surface) table and the total tag count.
    
    Renders the dossier's `connection_surface` into a Rich table and prints a header, the table, and a summary line showing the total number of tags across the seven connection-surface categories.
    
    Parameters:
        dossier (Any): Operator dossier object convertible by `operator_dossier_to_dict` and containing a `connection_surface` key.
    """
    table, total_tags = _render_connection_surface_table(
        operator_dossier_to_dict(dossier)["connection_surface"]
    )
    console.print("[bold]Operator Connection Surface (Layer 5)[/bold]")
    console.print(table)
    console.print(
        f"\n[bold]Total tags:[/bold] {total_tags} across 7 categories"
    )


@dossier_app.command("init")
def dossier_init(
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite an existing dossier file.",
    )
):
    """
    Create an operator dossier file populated with capability data inferred from configured repositories.
    
    Writes a skeleton dossier to ~/.prime-directive/operator_dossier.yaml containing auto-populated sections (capabilities, identity programming languages, connection surface tags, etc.). If a dossier file already exists the command aborts unless `force` is true. After writing, prints a summary of scanned repositories, detected skills/projects, and items that still require manual input.
    
    Parameters:
    	force (bool): If true, overwrite an existing dossier file.
    """
    dossier_path = get_dossier_path()
    if dossier_path.exists() and not force:
        console.print(
            f"[bold yellow]Dossier already exists:[/bold yellow] {dossier_path}"
        )
        console.print("Use `pd dossier init --force` to overwrite it.")
        raise typer.Exit(code=1)

    console.print(
        Panel.fit(
            "This will create ~/.prime-directive/operator_dossier.yaml\n"
            "with a skeleton structure and auto-populated capability data.",
            title="PRIME DIRECTIVE — Operator Dossier Setup",
            border_style="blue",
        )
    )
    cfg = load_config()
    empire = load_empire_if_exists(cfg)
    console.print("Pre-populating from your configured repositories...")
    dossier, summaries, proposals = _bootstrap_dossier(cfg)
    written_path = write_operator_dossier(dossier, dossier_path)
    source_file_count = sum(len(summary.source_files) for summary in summaries)
    skill_proposal_count = sum(
        1 for proposal in proposals if proposal.action == "add_skill"
    )
    project_proposal_count = sum(
        1 for proposal in proposals if proposal.action == "add_project"
    )
    console.print(f"  Found {len(cfg.repos)} repos in config.yaml")
    if empire is not None:
        console.print(
            f"  Found {len(empire.projects)} projects in empire.yaml"
        )
    console.print(
        f"  Scanned {source_file_count} dependency file(s) across configured repos"
    )
    console.print(
        f"\n[bold green]Skeleton written to[/bold green] {written_path}"
    )
    console.print("\n[bold]Auto-populated:[/bold]")
    console.print(
        f"  capabilities.projects_built: {len(dossier.capabilities.projects_built)} project(s) from {project_proposal_count} proposal(s)"
    )
    console.print(
        f"  capabilities.skills: {len(dossier.capabilities.skills)} detected skill(s) from {skill_proposal_count} proposal(s)"
    )
    console.print(
        f"  identity.languages.programming: {len(dossier.identity.languages.get('programming', []))} detected language(s)"
    )
    console.print(
        f"  connection_surface.topic_tags: {len(dossier.connection_surface.topic_tags)} derived tag(s)"
    )
    console.print("\n[bold]Still needs your input:[/bold]")
    console.print(
        "  identity (education, military, hobbies, values, publications)"
    )
    console.print("  network (companies, industries, collaborators, overlaps)")
    console.print(
        "  positioning (statement, offerings, case studies, revenue model)"
    )
    console.print("  connection_surface.philosophy_tags (manual only)")
    console.print(
        "\n[bold blue]Tip:[/bold blue] Run `pd dossier validate` after editing to check for errors."
    )


@empire_app.command("init")
def empire_init(
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing empire.yaml"
    ),
) -> None:
    """
    Create a scaffolded empire.yaml file at the user's ~/.prime-directive/empire.yaml path.
    
    Parameters:
    	force (bool): If True, overwrite an existing empire.yaml; otherwise abort if the file exists.
    """
    from prime_directive.core.empire import (
        get_empire_path,
        ProjectRole,
        StrategicWeight,
    )

    empire_path = get_empire_path()
    if empire_path.exists() and not force:
        console.print(
            f"[bold red]empire.yaml already exists:[/bold red] {empire_path}"
        )
        console.print("Use --force to overwrite.")
        raise typer.Exit(code=1)

    cfg = load_config()
    repo_ids = list(getattr(cfg, "repos", {}).keys())

    skeleton: dict = {
        "version": "3.0",
        "projects": {},
    }
    for repo_id in repo_ids:
        skeleton["projects"][repo_id] = {
            "domain": "",
            "role": ProjectRole.RESEARCH.value,
            "strategic_weight": StrategicWeight.MEDIUM.value,
            "description": "",
            "depends_on": [],
        }

    empire_path.parent.mkdir(parents=True, exist_ok=True)
    import yaml as _yaml

    with empire_path.open("w", encoding="utf-8") as fh:
        _yaml.safe_dump(skeleton, fh, sort_keys=False, allow_unicode=True)

    console.print(
        f"[bold green]Empire skeleton written to[/bold green] {empire_path}"
    )
    console.print(
        f"  {len(repo_ids)} repo(s) scaffolded. "
        "Edit role/strategic_weight/description/depends_on for each project."
    )
    roles = ", ".join(r.value for r in ProjectRole)
    weights = ", ".join(w.value for w in StrategicWeight)
    console.print(f"  Valid roles: {roles}")
    console.print(f"  Valid weights: {weights}")


@dossier_app.command("validate")
def dossier_validate():
    """
    Validate the operator dossier file and report any errors, warnings, or informational messages.
    
    If tag-normalization suggestions are discovered the user is prompted to apply them; when accepted, the dossier file may be modified on disk and re-validated. Validation results are printed to the console. On validation failure the command exits the process.
    
    Raises:
        typer.Exit: Exits with code 1 when validation fails.
    """
    dossier_path = get_dossier_path()
    report, raw_data = validate_operator_dossier_file(dossier_path)
    normalization_fixes = (
        preview_operator_dossier_tag_normalization_fixes(raw_data)
        if raw_data
        else []
    )
    if normalization_fixes:
        console.print(
            "\n[bold yellow]Tag normalization fixes available[/bold yellow]"
        )
        for item in normalization_fixes:
            console.print(f"  - {item}")
        if typer.confirm(
            "Apply suggested tag normalization fixes?", default=True
        ):
            applied_fixes = apply_operator_dossier_tag_normalization_fixes(
                raw_data
            )
            if applied_fixes:
                import yaml as _yaml

                dossier_path.write_text(
                    _yaml.safe_dump(raw_data, sort_keys=False),
                    encoding="utf-8",
                )
                console.print(
                    f"\n[bold green]Applied {len(applied_fixes)} tag normalization fix(es).[/bold green]"
                )
                report, raw_data = validate_operator_dossier_file(dossier_path)

    console.print("[bold]Operator Dossier Validation[/bold]")
    console.print(f"Path: {dossier_path}", soft_wrap=True)

    if report.errors:
        console.print("\n[bold red]Errors[/bold red]")
        for item in report.errors:
            console.print(f"  - {item}")

    if report.warnings:
        console.print("\n[bold yellow]Warnings[/bold yellow]")
        for item in report.warnings:
            console.print(f"  - {item}")

    if report.info:
        console.print("\n[bold blue]Info[/bold blue]")
        for item in report.info:
            console.print(f"  - {item}")

    summary = (
        f"errors={len(report.errors)} "
        f"warnings={len(report.warnings)} "
        f"info={len(report.info)}"
    )
    if report.is_valid:
        console.print(
            f"\n[bold green]Validation passed[/bold green] ({summary})"
        )
        return

    console.print(f"\n[bold red]Validation failed[/bold red] ({summary})")
    raise typer.Exit(code=1)


@dossier_app.command("sync-skills")
def dossier_sync_skills(
    ctx: typer.Context,
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Persist all proposed skill, project, and theme additions.",
    ),
    dry_run: bool = typer.Option(
        True,
        "--dry-run",
        help="Show proposals without modifying the dossier. Default behavior.",
    ),
    deep: bool = typer.Option(
        False,
        "--deep",
        help="Analyze recent snapshot text for repeated domain themes.",
    ),
):
    """
    Scan configured repositories, propose skill and project updates for the operator dossier, optionally run a deep LLM-based analysis of recent snapshots, and (when requested) apply the proposals to the dossier file.
    
    Parameters:
        ctx (typer.Context): CLI context used to detect how options were provided.
        apply (bool): When true, persist proposed skill, project, and theme changes to the dossier.
        dry_run (bool): When true, show proposals without modifying the dossier (default behavior).
        deep (bool): When true, analyze recent DB snapshot text to produce LLM-generated theme suggestions.
    
    Raises:
        typer.BadParameter: If both `--apply` and `--dry-run` are passed explicitly.
        typer.Exit: If the dossier file is missing or a deep analysis error occurs.
    """
    dry_run_explicit = (
        ctx.get_parameter_source("dry_run") == ParameterSource.COMMANDLINE
    )
    if apply and dry_run_explicit:
        raise typer.BadParameter(
            "`--apply` and `--dry-run` cannot be used together."
        )

    cfg = load_config()
    dossier_path = get_dossier_path()
    if not dossier_path.exists():
        console.print(
            f"[bold red]Dossier file not found:[/bold red] {dossier_path}"
        )
        console.print("Run `pd dossier init` first.")
        raise typer.Exit(code=1)

    dossier = load_operator_dossier(dossier_path)
    summaries, proposals = build_sync_proposals(cfg, dossier)
    theme_suggestions: list[Any] = []
    deep_error: Optional[str] = None
    deep_snapshot_count = 0
    deep_repo_count = 0
    deep_cost_line: Optional[str] = None
    if deep:
        snapshot_texts, deep_snapshot_count, deep_repo_count = asyncio.run(
            _load_recent_snapshot_texts(cfg.system.db_path)
        )
        ai_model = getattr(cfg.system, "ai_model", "qwen2.5-coder")
        ai_provider = getattr(cfg.system, "ai_provider", "ollama")
        fallback_provider = getattr(
            cfg.system,
            "ai_fallback_provider",
            "none",
        )
        fallback_model = getattr(
            cfg.system, "ai_fallback_model", "gpt-4o-mini"
        )
        require_confirmation = getattr(
            cfg.system,
            "ai_require_confirmation",
            True,
        )
        openai_api_url = getattr(
            cfg.system,
            "openai_api_url",
            "https://api.openai.com/v1/chat/completions",
        )
        openai_timeout_seconds = getattr(
            cfg.system, "openai_timeout_seconds", 10.0
        )
        openai_max_tokens = getattr(cfg.system, "openai_max_tokens", 150)
        ollama_api_url = getattr(
            cfg.system,
            "ollama_api_url",
            "http://localhost:11434/api/generate",
        )
        ollama_timeout_seconds = getattr(
            cfg.system, "ollama_timeout_seconds", 5.0
        )
        ollama_max_retries = getattr(cfg.system, "ollama_max_retries", 0)
        ollama_backoff_seconds = getattr(
            cfg.system, "ollama_backoff_seconds", 0.0
        )
        ai_monthly_budget_usd = getattr(
            cfg.system, "ai_monthly_budget_usd", 10.0
        )
        ai_cost_per_1k_tokens = getattr(
            cfg.system, "ai_cost_per_1k_tokens", 0.002
        )
        theme_suggestions, deep_metadata, deep_error = asyncio.run(
            generate_theme_suggestions_with_ai(
                snapshot_texts=snapshot_texts,
                existing_tags=dossier.capabilities.domain_expertise,
                model=ai_model,
                provider=ai_provider,
                fallback_provider=fallback_provider,
                fallback_model=fallback_model,
                require_confirmation=require_confirmation,
                openai_api_url=openai_api_url,
                openai_timeout_seconds=openai_timeout_seconds,
                openai_max_tokens=openai_max_tokens,
                api_url=ollama_api_url,
                timeout_seconds=ollama_timeout_seconds,
                max_retries=ollama_max_retries,
                backoff_seconds=ollama_backoff_seconds,
                db_path=cfg.system.db_path,
                monthly_budget_usd=ai_monthly_budget_usd,
                cost_per_1k_tokens=ai_cost_per_1k_tokens,
            )
        )
        if deep_error is not None:
            console.print(
                f"[bold red]Deep analysis error:[/bold red] {deep_error}"
            )
            raise typer.Exit(code=1)
        if deep_metadata is not None:
            total_tokens = (
                deep_metadata.input_tokens + deep_metadata.output_tokens
            )
            deep_cost_line = f"Cost: {total_tokens} tokens (${deep_metadata.cost_estimate_usd:.4f})"

    console.print("[bold]Operator Dossier Skill Sync[/bold]")
    if summaries:
        scan_table = Table(title="Repository Scan Summary")
        scan_table.add_column("Repo")
        scan_table.add_column("Files")
        scan_table.add_column("Detected Skills")
        for summary in summaries:
            scan_table.add_row(
                summary.repo_id,
                ", ".join(summary.source_files) or "-",
                ", ".join(summary.detected_skills) or "-",
            )
        console.print(scan_table)

    proposal_table = Table(title="Proposals")
    proposal_table.add_column("Action")
    proposal_table.add_column("Repo")
    proposal_table.add_column("Value")
    proposal_table.add_column("Source")
    proposal_table.add_column("Confidence")
    for proposal in proposals:
        proposal_table.add_row(
            proposal.action,
            proposal.repo_id,
            proposal.value_name,
            proposal.source,
            f"{proposal.confidence:.2f}",
        )
    console.print(proposal_table)
    skill_proposal_count = sum(
        1 for proposal in proposals if proposal.action == "add_skill"
    )
    project_proposal_count = sum(
        1 for proposal in proposals if proposal.action == "add_project"
    )

    if deep:
        console.print(
            f"\n[bold]Deep Analysis (LLM)[/bold]\n\n  Scanned {deep_snapshot_count} snapshots across {deep_repo_count} repos (last 30 days)"
        )
        if deep_error:
            console.print(f"[bold red]{deep_error}[/bold red]")
        elif theme_suggestions:
            theme_table = Table(title="Deep Theme Suggestions")
            theme_table.add_column("Tag")
            theme_table.add_column("Occurrences")
            theme_table.add_column("Evidence")
            theme_table.add_column("Confidence")
            for suggestion in theme_suggestions:
                theme_table.add_row(
                    suggestion.tag,
                    str(suggestion.occurrences),
                    suggestion.sample,
                    f"{suggestion.confidence:.2f}",
                )
            console.print(theme_table)
        else:
            console.print(
                "[bold blue]No deep theme suggestions found.[/bold blue]"
            )
        if deep_cost_line is not None:
            console.print(f"\n  {deep_cost_line}")

    console.print("\n[bold]Summary[/bold]")
    console.print(f"  {skill_proposal_count} new skill proposal(s)")
    console.print(f"  {project_proposal_count} new project proposal(s)")
    console.print(f"  {len(theme_suggestions)} theme suggestion(s)")

    if not proposals and not theme_suggestions:
        console.print(
            "[bold green]No new skill, project, or theme proposals found.[/bold green]"
        )
        return

    if not apply:
        console.print(
            "[bold blue]Dry run only.[/bold blue] Re-run with `pd dossier sync-skills --apply` to persist changes."
        )
        return

    apply_sync_proposals(dossier, proposals)
    _seed_programming_languages(dossier, summaries)
    existing_domain_tags = {
        tag.strip().lower()
        for tag in dossier.capabilities.domain_expertise
        if tag.strip()
    }
    applied_theme_count = 0
    for suggestion in theme_suggestions:
        normalized = suggestion.tag.strip().lower()
        if normalized in existing_domain_tags:
            continue
        dossier.capabilities.domain_expertise.append(suggestion.tag)
        existing_domain_tags.add(normalized)
        applied_theme_count += 1
    sync_connection_surface(dossier)
    write_operator_dossier(dossier, dossier_path)
    console.print(
        f"[bold green]Applied {len(proposals) + applied_theme_count} proposal(s)[/bold green] to {dossier_path}"
    )


@dossier_app.command("sync-tags")
def dossier_sync_tags():
    """
    Regenerates Layer 5 connection-surface tags from Layers 1–4 and writes the updated dossier to disk.
    
    If the dossier file is missing the command exits with code 1. Philosophy tags are preserved as manual; a category-by-category summary and total tag counts are printed to the console after writing.
    """
    dossier_path = get_dossier_path()
    if not dossier_path.exists():
        console.print(
            f"[bold red]Dossier file not found:[/bold red] {dossier_path}"
        )
        console.print("Run `pd dossier init` first.")
        raise typer.Exit(code=1)

    dossier = load_operator_dossier(dossier_path)
    before_surface = operator_dossier_to_dict(dossier)["connection_surface"]
    sync_connection_surface(dossier)
    after_surface = operator_dossier_to_dict(dossier)["connection_surface"]
    summary_table = Table(title="Tag Sync Summary")
    summary_table.add_column("Category")
    summary_table.add_column("Before")
    summary_table.add_column("After")
    summary_table.add_column("Change")
    total_before = 0
    total_after = 0
    for field_name in [
        "experience_tags",
        "topic_tags",
        "geographic_tags",
        "education_tags",
        "industry_tags",
        "hobby_tags",
        "philosophy_tags",
    ]:
        before_tags = before_surface.get(field_name, [])
        after_tags = after_surface.get(field_name, [])
        total_before += len(before_tags)
        total_after += len(after_tags)
        if field_name == "philosophy_tags":
            change = "preserved, manual"
        else:
            added = sorted(set(after_tags) - set(before_tags))
            removed = sorted(set(before_tags) - set(after_tags))
            if added and removed:
                change = f"+{len(added)} / -{len(removed)}"
            elif added:
                change = f"+{len(added)}: {', '.join(added[:3])}"
            elif removed:
                change = f"-{len(removed)}: {', '.join(removed[:3])}"
            else:
                change = "unchanged"
        summary_table.add_row(
            field_name,
            str(len(before_tags)),
            str(len(after_tags)),
            change,
        )
    write_operator_dossier(dossier, dossier_path)
    console.print(
        "[bold]Tag Sync — Deriving connection_surface from Layers 1-4[/bold]"
    )
    console.print(summary_table)
    console.print(f"[bold]Total:[/bold] {total_before} → {total_after} tag(s)")
    console.print(f"[bold green]Updated[/bold green] {dossier_path}")


@dossier_app.command("show")
def dossier_show(
    layer: Optional[int] = typer.Option(
        None,
        "--layer",
        help="Show only a specific dossier layer (1-5).",
    ),
    tags_only: bool = typer.Option(
        False,
        "--tags-only",
        help="Show only Layer 5 connection-surface tags.",
    ),
):
    """
    Render the operator dossier to the terminal.
    
    Parameters:
        layer (Optional[int]): If provided, display only the specified dossier layer (1–5).
        tags_only (bool): If true, display only Layer 5 connection-surface tags; this option takes precedence over `layer`.
    """
    dossier_path = get_dossier_path()
    if not dossier_path.exists():
        console.print(
            f"[bold red]Dossier file not found:[/bold red] {dossier_path}"
        )
        console.print("Run `pd dossier init` first.")
        raise typer.Exit(code=1)

    dossier = load_operator_dossier(dossier_path)

    if tags_only:
        _print_connection_surface_layer(dossier)
        return

    if layer is not None:
        layer_mapping = {
            1: "identity",
            2: "capabilities",
            3: "network",
            4: "positioning",
            5: "connection_surface",
        }
        section_name = layer_mapping.get(layer)
        if section_name is None:
            console.print(
                "[bold red]Layer must be between 1 and 5.[/bold red]"
            )
            raise typer.Exit(code=1)
        if layer == 2:
            _print_capabilities_layer(dossier)
            return
        if layer == 1:
            _print_identity_layer(dossier)
            return
        if layer == 3:
            _print_network_layer(dossier)
            return
        if layer == 4:
            _print_positioning_layer(dossier)
            return
        if layer == 5:
            _print_connection_surface_layer(dossier)
            return
        return

    console.print("[bold]Operator Dossier[/bold]")
    console.print()
    _print_identity_layer(dossier)
    console.print()
    _print_capabilities_layer(dossier)
    console.print()
    _print_network_layer(dossier)
    console.print()
    _print_positioning_layer(dossier)
    console.print()
    _print_connection_surface_layer(dossier)


@dossier_app.command("export")
def dossier_export(
    format: str = typer.Option(
        "json",
        "--format",
        help="Output format: json, yaml, or tags-only.",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        help="Write the export to a file instead of stdout.",
    ),
    layer5_only: bool = typer.Option(
        False,
        "--layer5-only",
        help="Export only the connection_surface payload.",
    ),
):
    """
    Export the operator dossier in the requested format to stdout or a file.
    
    Supported formats (case-insensitive): "json", "yaml", and "tags-only". When
    `layer5_only` is true, the export contains only the dossier `version` and
    `connection_surface` payload.
    
    Parameters:
        format (str): Output format: "json", "yaml", or "tags-only".
        output (Optional[Path]): If provided, write the export to this file; otherwise
            print the export to stdout.
        layer5_only (bool): When true, include only the `version` and
            `connection_surface` fields in the exported payload.
    
    Notes:
        Exits with a non-zero code if the dossier file is missing or an unsupported
        format is requested.
    """
    dossier_path = get_dossier_path()
    if not dossier_path.exists():
        console.print(
            f"[bold red]Dossier file not found:[/bold red] {dossier_path}"
        )
        console.print("Run `pd dossier init` first.")
        raise typer.Exit(code=1)

    dossier = load_operator_dossier(dossier_path)
    data = operator_dossier_to_dict(dossier)

    if layer5_only:
        export_payload = {
            "version": data["version"],
            "connection_surface": data["connection_surface"],
        }
    else:
        export_payload = data

    normalized_format = format.strip().lower()
    if normalized_format == "json":
        payload_text = json.dumps(export_payload, indent=2, sort_keys=False)
    elif normalized_format == "yaml":
        payload_text = yaml.safe_dump(
            export_payload,
            sort_keys=False,
            allow_unicode=True,
        )
    elif normalized_format == "tags-only":
        payload_text = "\n".join(
            f"{key}: {', '.join(values) or '-'}"
            for key, values in data["connection_surface"].items()
        )
    else:
        console.print(
            "[bold red]Format must be `json`, `yaml`, or `tags-only`.[/bold red]"
        )
        raise typer.Exit(code=1)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload_text, encoding="utf-8")
        console.print(f"[bold green]Exported dossier[/bold green] to {output}")
        return

    typer.echo(payload_text)


# Initialize logging globally with default, will be re-configured if needed
setup_logging()


async def freeze_logic(
    repo_id: str,
    config: DictConfig,
    human_note: Optional[str] = None,
    human_objective: Optional[str] = None,
    human_blocker: Optional[str] = None,
    human_next_step: Optional[str] = None,
    skip_terminal_capture: bool = False,
    use_hq_model: bool = False,
):
    """
    Freeze the current repository context, generate an AI SITREP, and persist a ContextSnapshot to the database.

    Captures repository git state, terminal state (unless skipped), and active task; generates an AI SITREP using configured AI provider/model (optionally using the HQ model), and saves a ContextSnapshot (creating the Repository record if missing). Prints summary output to the console.

    Parameters:
        repo_id (str): Identifier of the repository to freeze as defined in `config.repos`.
        config (DictConfig): Composed Hydra configuration object with system and repo settings.
        human_note (Optional[str]): Optional free-form note to attach to the snapshot.
        human_objective (Optional[str]): Optional human-provided objective to include in the SITREP and snapshot.
        human_blocker (Optional[str]): Optional human-provided blocker to include in the SITREP and snapshot.
        human_next_step (Optional[str]): Optional human-provided next step to include in the SITREP and snapshot.
        skip_terminal_capture (bool): If True, do not attempt to capture terminal state and store placeholder values.
        use_hq_model (bool): If True, prefer the configured high-quality model/provider for SITREP generation.

    Raises:
        ValueError: If `repo_id` is not present in `config.repos`.
    """
    candidate = _normalize_repo_id(repo_id)
    if candidate not in config.repos:
        matches = difflib.get_close_matches(
            candidate,
            list(config.repos.keys()),
            n=1,
            cutoff=0.6,
        )
        msg = f"Repository '{repo_id}' not found in configuration."
        if matches:
            msg = f"{msg} Did you mean '{matches[0]}'?"
        console.print(f"[bold red]Error:[/bold red] {msg}")
        logger.error(msg)
        raise ValueError(msg)

    repo_id = candidate
    repo_config = config.repos[repo_id]
    repo_path = repo_config.path

    logger.info(f"Freezing context for {repo_id} at {repo_path}")
    console.print(f"[bold blue]Freezing context for {repo_id}...[/bold blue]")

    # 1. Capture Git State (Sync/Blocking)
    # 2. Capture Terminal State (Sync/Blocking)
    # These operations are independent and can be executed concurrently.
    git_st: GitStatus
    if config.system.mock_mode:
        logger.info("MOCK MODE: Skipping actual git status check")
        git_summary = "MOCK: Branch: main\nDirty: False"
        git_st = {
            "branch": "main",
            "is_dirty": False,
            "uncommitted_files": [],
            "diff_stat": "",
        }

        logger.info("MOCK MODE: Skipping terminal capture")
        last_cmd = "mock_cmd"
        term_output = "MOCK: Terminal output"
    elif skip_terminal_capture:
        git_st = await get_status(repo_path)
        git_summary = (
            f"Branch: {git_st['branch']}\n"
            f"Dirty: {git_st['is_dirty']}\n"
            f"Files: {git_st['uncommitted_files']}\n"
            f"Diff: {git_st.get('diff_stat', '')}"
        )

        last_cmd = "unknown"
        term_output = "Terminal capture skipped."
    else:
        git_task = asyncio.create_task(get_status(repo_path))
        term_task = asyncio.create_task(capture_terminal_state(repo_id))

        try:
            git_result, term_result = await asyncio.gather(
                git_task,
                term_task,
                return_exceptions=True,
            )
        except Exception as e:
            logger.exception(
                "Error running concurrent freeze capture steps",
                extra={"repo_id": repo_id},
            )
            git_result = e
            term_result = e

        if isinstance(git_result, BaseException):
            logger.warning(
                f"Git state capture failed for {repo_id}: {git_result!s}"
            )
            git_st = {
                "branch": "error",
                "is_dirty": False,
                "uncommitted_files": [],
                "diff_stat": str(git_result),
            }
        else:
            git_st = git_result

        git_summary = (
            f"Branch: {git_st['branch']}\n"
            f"Dirty: {git_st['is_dirty']}\n"
            f"Files: {git_st['uncommitted_files']}\n"
            f"Diff: {git_st.get('diff_stat', '')}"
        )

        if isinstance(term_result, BaseException):
            logger.warning(
                f"Terminal capture failed for {repo_id}: {term_result!s}"
            )
            last_cmd = "unknown"
            term_output = "Unexpected error during terminal capture."
        else:
            last_cmd, term_output = term_result

    logger.debug(f"Git state for {repo_id}: {git_st}")
    logger.debug(f"Terminal state: cmd={last_cmd}")

    # 3. Capture Active Task (Sync)
    active_task = get_active_task(repo_path)
    logger.debug(f"Active task: {active_task}")

    # 4. Generate AI SITREP (Blocking Network Call - could be made async
    # with httpx)
    console.print("Generating AI SITREP...")
    if config.system.mock_mode:
        logger.info("MOCK MODE: Skipping AI generation")
        sitrep = "MOCK: SITREP generated without AI."
    else:
        if use_hq_model:
            selected_model = getattr(
                config.system,
                "ai_model_hq",
                config.system.ai_model,
            )
            selected_provider = "openai"
        else:
            selected_model = config.system.ai_model
            selected_provider = config.system.ai_provider

        monthly_budget = getattr(config.system, "ai_monthly_budget_usd", 10.0)
        cost_per_1k = getattr(config.system, "ai_cost_per_1k_tokens", 0.002)

        sitrep = await generate_sitrep(
            repo_id=repo_id,
            git_state=git_summary,
            terminal_logs=term_output,
            active_task=active_task,
            human_objective=human_objective,
            human_blocker=human_blocker,
            human_next_step=human_next_step,
            human_note=human_note,
            model=selected_model,
            provider=selected_provider,
            fallback_provider=config.system.ai_fallback_provider,
            fallback_model=config.system.ai_fallback_model,
            require_confirmation=config.system.ai_require_confirmation,
            openai_api_url=config.system.openai_api_url,
            openai_timeout_seconds=config.system.openai_timeout_seconds,
            openai_max_tokens=config.system.openai_max_tokens,
            api_url=config.system.ollama_api_url,
            timeout_seconds=config.system.ollama_timeout_seconds,
            max_retries=config.system.ollama_max_retries,
            backoff_seconds=config.system.ollama_backoff_seconds,
            db_path=config.system.db_path,
            monthly_budget_usd=monthly_budget,
            cost_per_1k_tokens=cost_per_1k,
        )
    logger.info(f"Generated SITREP for {repo_id}")

    # 5. Save to DB (Async)
    await init_db(config.system.db_path)
    async for session in get_session(config.system.db_path):
        # Ensure Repository exists (FK constraint)
        from sqlalchemy import select as sql_select

        from prime_directive.core.db import Repository

        repo_id_col = cast(Any, Repository.id)
        stmt = sql_select(Repository).where(repo_id_col == repo_id)
        result = await session.execute(stmt)
        existing_repo = result.scalars().first()
        if not existing_repo:
            new_repo = Repository(
                id=repo_id,
                path=repo_path,
                priority=repo_config.priority,
                active_branch=repo_config.active_branch,
            )
            session.add(new_repo)
            await session.flush()

        snapshot = ContextSnapshot(
            repo_id=repo_id,
            timestamp=datetime.now(timezone.utc),
            git_status_summary=git_summary,
            terminal_last_command=last_cmd,
            terminal_output_summary=term_output,
            ai_sitrep=sitrep,
            human_note=human_note,
            human_objective=human_objective,
            human_blocker=human_blocker,
            human_next_step=human_next_step,
        )
        session.add(snapshot)
        await session.commit()
        msg = f"Snapshot saved. ID: {snapshot.id}"
        console.print(f"[bold green]{msg}[/bold green]")
        if human_objective:
            console.print(
                "[bold magenta]YOUR OBJECTIVE:[/bold magenta] "
                f"{human_objective}"
            )
        if human_blocker:
            console.print(
                "[bold magenta]YOUR BLOCKER:[/bold magenta] "
                f"{human_blocker}"
            )
        if human_next_step:
            console.print(
                "[bold magenta]YOUR NEXT STEP:[/bold magenta] "
                f"{human_next_step}"
            )
        if human_note:
            console.print(
                f"[bold magenta]YOUR NOTE:[/bold magenta] {human_note}"
            )
        console.print(f"[italic]{sitrep}[/italic]")
        logger.info(f"{msg}. SITREP: {sitrep}. Note: {human_note}")


@app.command("freeze")
def freeze(
    repo_id: str,
    objective: Optional[str] = typer.Option(
        None,
        "--objective",
        help="Primary objective of this session",
    ),
    blocker: Optional[str] = typer.Option(
        None,
        "--blocker",
        help="What didn't work / key uncertainty",
    ),
    next_step: Optional[str] = typer.Option(
        None,
        "--next-step",
        help="Next concrete action",
    ),
    note: Optional[str] = typer.Option(
        None,
        "--note",
        "-n",
        help="Optional: additional notes / brain dump",
    ),
    no_interview: bool = typer.Option(
        False,
        "--no-interview",
        help="Disable interactive interview prompts and use provided flags",
    ),
    hq: bool = typer.Option(
        False,
        "--hq",
        help="Use high-quality AI model (more expensive, better results)",
    ),
):
    """
    Create a repository snapshot (Git, terminal, and active task) and generate an AI SITREP.

    By default, this command runs an interactive interview to capture human context (objective, blocker, next step, and notes). Use `--no-interview` to skip prompts and supply values via flags.

    Parameters:
        repo_id (str): Identifier of the repository to snapshot.
        objective (Optional[str]): Primary focus for this session; included in the snapshot/SITREP.
        blocker (Optional[str]): Key blocker, uncertainty, or gotcha to record.
        next_step (Optional[str]): First concrete action to restart work, recorded as the next step.
        note (Optional[str]): Optional: additional notes / brain dump.
        no_interview (bool): If True, skip interactive prompts and use provided values as-is.
        hq (bool): If True, request the higher-quality (higher-cost) AI model for SITREP generation.
    """
    logger.info(f"Command: freeze {repo_id}")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    repo_id = _resolve_repo_id(repo_id, cfg)

    if not no_interview:
        if objective is None:
            entered = typer.prompt(
                "Context: What was your specific focus vs. the planned task?",
                default="",
                show_default=False,
            )
            objective = entered.strip() or None

        if blocker is None:
            entered = typer.prompt(
                "Mental Cache: What is the key blocker, uncertainty, or "
                "'gotcha'?",
                default="",
                show_default=False,
            )
            blocker = entered.strip() or None

        if next_step is None:
            entered = typer.prompt(
                "The Hook: What is the first 10-second action to restart?",
                default="",
                show_default=False,
            )
            next_step = entered.strip() or None

        if note is None:
            entered = typer.prompt(
                "Brain Dump: Any other context, warnings, or loose thoughts?",
                default="",
                show_default=False,
            )
            note = entered.strip() or None

    async def run_freeze():
        """
        Run the freeze logic for the selected repository and ensure DB engine disposal.

        Calls `freeze_logic` with the surrounding command options (note, objective, blocker, next_step, HQ flag). If `freeze_logic` raises a `ValueError`, exits the Typer command with code 1. Always disposes the database engine by awaiting `dispose_engine()` in a finally block.
        """
        try:
            await freeze_logic(
                repo_id,
                cfg,
                human_note=note,
                human_objective=objective,
                human_blocker=blocker,
                human_next_step=next_step,
                use_hq_model=hq,
            )
        except ValueError:
            raise typer.Exit(code=1) from None
        finally:
            await dispose_engine()

    asyncio.run(run_freeze())


@app.command("switch")
def switch(repo_id: str):
    """
    Switch the active workspace to another repository by freezing the current repo, performing the switch, and preparing the target repo.

    Raises:
        typer.Exit: With code 1 if `repo_id` is not present in configuration; with `_EXIT_CODE_SHELL_ATTACH` if the switch requires attaching a new shell.
    """
    logger.info(f"Command: switch {repo_id}")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    repo_id = _resolve_repo_id(repo_id, cfg)

    needs_shell_attach = run_switch(
        repo_id,
        cfg,
        cwd=os.getcwd(),
        freeze_fn=freeze_logic,
        ensure_session_fn=ensure_session,
        launch_editor_fn=launch_editor,
        init_db_fn=init_db,
        get_session_fn=get_session,
        dispose_engine_fn=dispose_engine,
        console=console,
        logger=logger,
    )

    if needs_shell_attach:
        raise typer.Exit(code=_EXIT_CODE_SHELL_ATTACH)


@app.command("install-hooks")
def install_hooks(repo_id: Optional[str] = typer.Argument(None)):
    """
    Install a Git post-commit hook that logs commits for a single configured repository or for all configured repositories.

    Creates a "post-commit" script under each target repository's .git/hooks directory that invokes the internal `pd _internal-log-commit <repo_id>` command, and makes the script executable.

    Parameters:
        repo_id (Optional[str]): If provided, install the hook only for the repository with this config ID; if `None`, install hooks for all repositories defined in the configuration.

    Raises:
        typer.Exit: Exits with code 1 if the specified repo_id is not found in the configuration, if the target path is not a Git repository (missing `.git`), or if filesystem operations fail while creating or writing the hook.
    """
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    if repo_id is not None:
        repo_id = _resolve_repo_id(repo_id, cfg)

    target_repo_ids = (
        [repo_id] if repo_id is not None else list(cfg.repos.keys())
    )

    for rid in target_repo_ids:
        repo_path = cfg.repos[rid].path
        git_dir = os.path.join(repo_path, ".git")
        hooks_dir = os.path.join(git_dir, "hooks")
        hook_path = os.path.join(hooks_dir, "post-commit")

        if not os.path.isdir(git_dir):
            msg = f"{rid}: not a git repo (missing .git): {repo_path}"
            console.print(f"[bold red]Error:[/bold red] {msg}")
            logger.error(msg)
            raise typer.Exit(code=1)

        try:
            os.makedirs(hooks_dir, exist_ok=True)

            script = (
                "#!/bin/sh\n"
                f"command pd _internal-log-commit {rid} "
                ">/dev/null 2>&1 || true\n"
            )
            with open(hook_path, "w", encoding="utf-8") as f:
                f.write(script)

            os.chmod(hook_path, 0o755)

            console.print(
                f"[green]Installed post-commit hook:[/green] {hook_path}"
            )
            logger.info(f"Installed post-commit hook for {rid}: {hook_path}")
        except OSError as e:
            msg = f"{rid}: failed to install post-commit hook: {e}"
            console.print(f"[bold red]Error:[/bold red] {msg}")
            logger.exception(msg)
            raise typer.Exit(code=1) from None


@app.command("_internal-log-commit", hidden=True)
def internal_log_commit(repo_id: str):
    """
    Record a commit event for the given repository in the application's event log.

    This creates and persists an EventLog entry with EventType.COMMIT associated with the provided repository identifier using the configured database, and ensures database resources are cleaned up.

    Parameters:
        repo_id (str): Identifier of the repository to associate with the commit event.
    """
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    async def run_internal():
        """
        Record a commit event for the current repository in the application's database.

        Initializes the database connection, inserts an EventLog with EventType.COMMIT for the enclosing `repo_id`, commits the change, and ensures the database engine is disposed on exit.
        """
        try:
            await init_db(cfg.system.db_path)
            async for session in get_session(cfg.system.db_path):
                session.add(
                    EventLog(
                        repo_id=repo_id,
                        event_type=EventType.COMMIT,
                    )
                )
                await session.commit()
        finally:
            await dispose_engine()

    asyncio.run(run_internal())


def _format_seconds(seconds: float) -> str:
    """
    Format a duration in seconds into a compact human-readable string.

    Converts the given number of seconds to hours, minutes, and seconds and returns:
    - "HhMMmSSs" when one hour or more,
    - "MmSSs" when at least one minute but less than an hour,
    - "Ss" when less than one minute.

    Parameters:
        seconds (float): Duration in seconds.

    Returns:
        str: Formatted duration string, e.g. "1h02m03s", "12m34s", or "45s".
    """
    seconds_int = round(seconds)
    hours, rem = divmod(seconds_int, 3600)
    minutes, secs = divmod(rem, 60)
    if hours > 0:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    if minutes > 0:
        return f"{minutes}m{secs:02d}s"
    return f"{secs}s"


@app.command("metrics")
def metrics(repo_id: Optional[str] = typer.Option(None, "--repo")):
    """
    Display time-to-commit metrics for one or all configured repositories.

    Calculates intervals between a SWITCH_IN event and the next COMMIT event to derive average and most recent time-to-commit (TTC) and the number of samples for each repository, then prints a summary table to the console. When a `repo_id` is provided, metrics are limited to that repository.
    Parameters:
        repo_id (Optional[str]): Repository identifier to limit the report to a single repository; when omitted, metrics for all configured repositories are shown.
    """
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    if repo_id is not None:
        repo_id = _resolve_repo_id(repo_id, cfg)

    async def run_metrics():
        """
        Compute and display time-to-commit (TTC) metrics for one or all repositories.

        Initializes the database, collects EventLog entries for the specified repo_id (or all repos if none provided), computes intervals from each SWITCH_IN event to the next COMMIT event, and prints a table showing the average TTC, the most recent TTC, and the sample count for each repository. Ensures the database engine is disposed on completion.
        """
        try:
            await init_db(cfg.system.db_path)

            target_repo_ids = (
                [repo_id] if repo_id is not None else list(cfg.repos.keys())
            )

            table = Table(title="Prime Directive Metrics")
            table.add_column("Repo", style="cyan")
            table.add_column("TTC avg", style="green")
            table.add_column("TTC recent", style="magenta")
            table.add_column("Samples", justify="right")

            async for session in get_session(cfg.system.db_path):
                for rid in target_repo_ids:
                    stmt = (
                        select(EventLog)
                        .where(EventLog.repo_id == rid)
                        .order_by(EventLog.timestamp.asc())
                    )
                    result = await session.execute(stmt)
                    events = list(result.scalars().all())

                    deltas: list[float] = []
                    last_switch_ts: Optional[datetime] = None
                    for ev in events:
                        if ev.event_type == EventType.SWITCH_IN:
                            last_switch_ts = ev.timestamp
                        elif (
                            ev.event_type == EventType.COMMIT
                            and last_switch_ts is not None
                        ):
                            delta = (
                                ev.timestamp - last_switch_ts
                            ).total_seconds()
                            if delta >= 0:
                                deltas.append(delta)
                            last_switch_ts = None

                    if deltas:
                        avg = sum(deltas) / len(deltas)
                        recent = deltas[-1]
                        table.add_row(
                            rid,
                            _format_seconds(avg),
                            _format_seconds(recent),
                            str(len(deltas)),
                        )
                    else:
                        table.add_row(rid, "-", "-", "0")

            console.print(table)
        finally:
            await dispose_engine()

    asyncio.run(run_metrics())


@app.command("list")
def list_repos():
    """
    Display a table of all managed repositories.

    Prints a Rich table showing each repository's ID, priority, active branch (or "N/A"), and filesystem path. Repositories are sorted by priority in descending order.
    """
    logger.info("Command: list")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    table = Table(title="Prime Directive Repositories")
    table.add_column("ID", style="cyan")
    table.add_column("Priority", style="magenta")
    table.add_column("Branch", style="green")
    table.add_column("Path", style="yellow")

    # Sort by priority descending
    sorted_repos = sorted(
        cfg.repos.values(),
        key=lambda r: r.priority,
        reverse=True,
    )

    for repo in sorted_repos:
        table.add_row(
            repo.id,
            str(repo.priority),
            repo.active_branch or "N/A",
            repo.path,
        )
    console.print(table)


@app.command("status")
def status_command():
    """Show detailed status of all repositories."""
    logger.info("Command: status")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    table = Table(title="Prime Directive Status")
    table.add_column("Project", style="cyan")
    table.add_column("Priority", justify="center")
    table.add_column("Branch", style="green")
    table.add_column("Git Status", style="bold")
    table.add_column("Last Snapshot", style="blue")

    sorted_repos = sorted(
        cfg.repos.values(),
        key=lambda r: r.priority,
        reverse=True,
    )

    async def run_status():
        """
        Collects repository statuses and populates the display table with git state and last snapshot timestamps.

        This coroutine initializes the database, iterates configured repositories, obtains each repository's git status and most recent ContextSnapshot timestamp, and adds a row to the shared table containing repository id, priority, branch, git status, and last snapshot time. The database engine is always disposed when finished.
        """
        try:
            # Ensure DB exists/tables created
            await init_db(cfg.system.db_path)

            async for session in get_session(cfg.system.db_path):
                # We can reuse this session for all queries

                for repo in sorted_repos:
                    # 1. Git Status (Sync)
                    if cfg.system.mock_mode:
                        git_st = {
                            "branch": "mock",
                            "is_dirty": False,
                            "uncommitted_files": [],
                        }
                    else:
                        git_st = await get_status(repo.path)

                    status_icon = "🟢"
                    status_text = "Clean"
                    if git_st["is_dirty"]:
                        status_icon = "🔴"
                        dirty_count = len(git_st["uncommitted_files"])
                        status_text = f"Dirty ({dirty_count})"
                    elif git_st["branch"] == "unknown":
                        status_icon = "⚪"
                        status_text = "Not Git"
                    elif git_st["branch"] == "error":
                        status_icon = "❌"
                        status_text = "Error"
                    elif git_st["branch"] == "timeout":
                        status_icon = "⏱️"
                        status_text = "Timeout"

                    git_display = f"{status_icon} {status_text}"

                    # 2. Last Snapshot (Async)
                    last_snap_str = "Never"
                    try:
                        stmt = (
                            select(ContextSnapshot)
                            .where(ContextSnapshot.repo_id == repo.id)
                            .order_by(ContextSnapshot.timestamp.desc())
                            .limit(1)
                        )
                        result = await session.execute(stmt)
                        snapshot = result.scalars().first()
                        if snapshot:
                            ts_fmt = "%Y-%m-%d %H:%M"
                            last_snap_str = snapshot.timestamp.strftime(ts_fmt)
                    except (OSError, ValueError) as e:
                        logger.warning(
                            f"Error fetching snapshot for {repo.id}: {e}"
                        )
                        last_snap_str = "Error"

                    if repo.priority >= 8:
                        priority_prefix = "🔥"
                    else:
                        priority_prefix = "⚡"
                    priority_display = f"{priority_prefix} {repo.priority}"
                    if isinstance(git_st["branch"], str):
                        branch_display = git_st["branch"]
                    else:
                        branch_display = "Unknown"

                    table.add_row(
                        repo.id,
                        priority_display,
                        branch_display,
                        git_display,
                        last_snap_str,
                    )
        finally:
            await dispose_engine()

    asyncio.run(run_status())
    console.print(table)


@app.command("sitrep")
def sitrep(
    repo_id: str,
    deep_dive: bool = typer.Option(
        False,
        "--deep-dive",
        help=(
            "Generate longitudinal summary from historical snapshots "
            "using HQ model"
        ),
    ),
    limit: int = typer.Option(
        5,
        "--limit",
        "-l",
        help="Number of historical snapshots to include (default: 5)",
    ),
):
    """
    Show a situational report (SITREP) for a repository.
    
    When called without deep-dive, display the latest snapshot's timestamp, any provided
    human fields (objective, blocker, next step, note), and the AI-generated summary.
    When `deep_dive` is True, compile a longitudinal narrative from up to `limit`
    historical snapshots and generate a concise deep-dive summary using the configured
    high-quality AI model (requires `OPENAI_API_KEY`).
    
    Parameters:
        repo_id (str): Identifier of the repository to inspect.
        deep_dive (bool): If True, perform a longitudinal deep-dive using the HQ model.
        limit (int): Maximum number of most-recent snapshots to include in the deep-dive.
    """
    logger.info(f"Command: sitrep {repo_id} (deep_dive={deep_dive})")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    repo_id = _resolve_repo_id(repo_id, cfg)

    async def run_sitrep():
        """
        Show recent context snapshots for a configured repository and optionally produce a concise longitudinal deep-dive SITREP.
        
        When run without deep-dive mode, prints the latest snapshot's timestamp, any human-provided fields (objective, blocker, next step, note), and the AI summary. When deep-dive mode is enabled, compiles a historical narrative from available snapshots (subject to a character budget) and requests a longitudinal summary from an HQ model; deep-dive requires an OpenAI API key. The function writes output to the console and always disposes the database engine on exit.
        """
        await init_db(cfg.system.db_path)
        try:
            async for session in get_session(cfg.system.db_path):
                repo_id_col = cast(Any, ContextSnapshot.repo_id)
                ts_col = cast(Any, ContextSnapshot.timestamp)
                stmt = (
                    select(ContextSnapshot)
                    .where(repo_id_col == repo_id)
                    .order_by(ts_col.desc())
                    .limit(limit)
                )
                result = await session.execute(stmt)
                snapshots = list(result.scalars().all())

                if not snapshots:
                    console.print(
                        f"[yellow]No snapshots found for {repo_id}[/yellow]"
                    )
                    return

                if not deep_dive:
                    # Just show the latest snapshot
                    latest = snapshots[0]
                    console.print(
                        f"\n[bold reverse] SITREP for {repo_id} "
                        "[/bold reverse]"
                    )
                    console.print(
                        f"[bold yellow]Timestamp:[/bold yellow] "
                        f"{latest.timestamp}"
                    )
                    if latest.human_objective:
                        console.print(
                            "[bold magenta]Objective:[/bold magenta] "
                            f"{latest.human_objective}"
                        )
                    if latest.human_blocker:
                        console.print(
                            "[bold magenta]Blocker:[/bold magenta] "
                            f"{latest.human_blocker}"
                        )
                    if latest.human_next_step:
                        console.print(
                            "[bold magenta]Next Step:[/bold magenta] "
                            f"{latest.human_next_step}"
                        )
                    if latest.human_note:
                        console.print(
                            "[bold magenta]Note:[/bold magenta] "
                            f"{latest.human_note}"
                        )
                    console.print(
                        "[bold cyan]AI Summary:[/bold cyan] "
                        f"{latest.ai_sitrep}"
                    )
                    return

                # Deep dive: compile historical narrative
                console.print(
                    "[bold blue]Generating deep-dive analysis for "
                    f"{repo_id}...[/bold blue]"
                )
                console.print(
                    f"[dim]Analyzing {len(snapshots)} historical snapshots..."
                    "[/dim]"
                )

                # Build historical narrative with a character budget
                # ~12 000 chars ≈ 3 000 tokens, leaving room for prompt overhead
                _MAX_NARRATIVE_CHARS = 12_000
                history_entries: list[str] = []
                chars_used = 0
                # Iterate newest-first so the budget keeps recent context
                for i, snap in enumerate(snapshots):
                    entry = f"--- Snapshot ({snap.timestamp}) ---\n"
                    if snap.human_objective:
                        entry += f"Objective: {snap.human_objective}\n"
                    if snap.human_blocker:
                        entry += f"Blocker: {snap.human_blocker}\n"
                    if snap.human_next_step:
                        entry += f"Next Step: {snap.human_next_step}\n"
                    if snap.human_note:
                        entry += f"Notes: {snap.human_note}\n"
                    entry += f"AI Summary: {snap.ai_sitrep}\n"
                    entry += f"Git State: {snap.git_status_summary}\n"
                    if chars_used + len(entry) > _MAX_NARRATIVE_CHARS:
                        omitted = len(snapshots) - i
                        history_entries.append(
                            f"[{omitted} older snapshot(s) omitted]"
                        )
                        break
                    history_entries.append(entry)
                    chars_used += len(entry)
                # Reverse so narrative reads oldest → newest
                history_entries.reverse()

                historical_narrative = "\n".join(history_entries)

                # Generate longitudinal summary using HQ model
                from prime_directive.core.ai_providers import (
                    generate_openai_chat,
                    get_openai_api_key,
                )

                api_key = get_openai_api_key()
                if not api_key:
                    console.print(
                        "[bold red]Error:[/bold red] OPENAI_API_KEY not set "
                        "(required for deep-dive)"
                    )
                    return

                system_prompt = (
                    "You are a senior engineering assistant "
                    "analyzing a developer's work history. "
                    "Given a series of timestamped context "
                    "snapshots, generate a comprehensive "
                    "longitudinal summary that: "
                    "1) Identifies the overarching goals, "
                    "2) Highlights what approaches were tried "
                    "and failed, "
                    "3) Notes key blockers and uncertainties, "
                    "4) Recommends the immediate next action "
                    "based on the trajectory. "
                    "Be specific and actionable. Max 200 words."
                )

                prompt = f"""
Repository: {repo_id}
Number of snapshots: {len(snapshots)}
Time span: {snapshots[-1].timestamp} to {snapshots[0].timestamp}

Historical Context (oldest to newest):
{historical_narrative}

Generate a longitudinal SITREP that helps the developer resume work
effectively.
"""

                hq_model = getattr(cfg.system, "ai_model_hq", "gpt-4o")
                try:
                    summary = await generate_openai_chat(
                        api_url=cfg.system.openai_api_url,
                        api_key=api_key,
                        model=hq_model,
                        system=system_prompt,
                        prompt=prompt,
                        timeout_seconds=30.0,
                        max_tokens=500,
                    )

                    console.print(
                        f"\n[bold reverse] DEEP-DIVE SITREP for {repo_id} "
                        "[/bold reverse]"
                    )

                    time_span = (
                        f"{snapshots[-1].timestamp} to "
                        f"{snapshots[0].timestamp}"
                    )
                    console.print(
                        f"[dim]Based on {len(snapshots)} snapshots from "
                        f"{time_span}"
                        "[/dim]"
                    )
                    console.print(f"\n[bold cyan]{summary}[/bold cyan]")
                except (httpx.HTTPError, ValueError, OSError) as e:
                    console.print(
                        "[bold red]Error generating deep-dive:[/bold red] "
                        f"{e}"
                    )
        finally:
            await dispose_engine()

    asyncio.run(run_sitrep())


@app.command("ai-usage")
def ai_usage():
    """
    Print a month-to-date AI usage and budget report to the console.

    Includes the total estimated cost and call count for the current month, the configured monthly budget and remaining balance with a color-coded usage warning, and a table of up to 10 recent AI call logs showing time, provider, model, tokens, cost, and success status.
    """
    logger.info("Command: ai-usage")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    from prime_directive.core.ai_providers import get_monthly_usage
    from prime_directive.core.db import AIUsageLog

    async def run_usage():
        """
        Display a month-to-date AI usage report and recent API calls.

        Queries stored AI usage metrics, prints totals (calls, cost, budget, remaining and usage percentage)
        and a table of recent API calls to the console, and ensures the database engine is initialized
        and disposed.
        """
        await init_db(cfg.system.db_path)
        try:
            # Get monthly totals
            total_cost, call_count = await get_monthly_usage(
                cfg.system.db_path
            )
            budget = getattr(cfg.system, "ai_monthly_budget_usd", 10.0)
            remaining = max(0, budget - total_cost)
            pct_used = (total_cost / budget * 100) if budget > 0 else 0

            console.print("\n[bold reverse] AI Usage Report [/bold reverse]")
            console.print("[bold]Month-to-Date (OpenAI):[/bold]")
            console.print(f"  Calls: {call_count}")
            console.print(f"  Cost:  ${total_cost:.4f}")
            console.print(f"  Budget: ${budget:.2f}")
            console.print(
                f"  Remaining: ${remaining:.4f} ({100-pct_used:.1f}%)"
            )

            if pct_used >= 90:
                console.print(
                    "  [bold red]⚠️  "
                    f"{pct_used:.1f}% of budget used!"
                    "[/bold red]"
                )
            elif pct_used >= 75:
                console.print(
                    "  [bold yellow]⚠️  "
                    f"{pct_used:.1f}% of budget used"
                    "[/bold yellow]"
                )
            else:
                console.print(
                    "  [green]✅ " f"{pct_used:.1f}% of budget used" "[/green]"
                )

            # Show recent calls
            async for session in get_session(cfg.system.db_path):
                now = datetime.now(timezone.utc)
                month_start = now.replace(
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )

                ts_col = cast(Any, AIUsageLog.timestamp)
                stmt = (
                    select(AIUsageLog)
                    .where(ts_col >= month_start)
                    .order_by(ts_col.desc())
                    .limit(10)
                )
                result = await session.execute(stmt)
                recent = list(result.scalars().all())

                if recent:
                    console.print("\n[bold]Recent Calls:[/bold]")
                    table = Table(show_header=True)
                    table.add_column("Time", style="dim")
                    table.add_column("Provider")
                    table.add_column("Model")
                    table.add_column("Tokens")
                    table.add_column("Cost")
                    table.add_column("Status")

                    for log in recent:
                        status = (
                            "[green]✓[/green]"
                            if log.success
                            else "[red]✗[/red]"
                        )
                        table.add_row(
                            log.timestamp.strftime("%m-%d %H:%M"),
                            log.provider,
                            log.model,
                            str(log.output_tokens),
                            f"${log.cost_estimate_usd:.4f}",
                            status,
                        )
                    console.print(table)
                break
        finally:
            await dispose_engine()

    asyncio.run(run_usage())


@app.command("doctor")
def doctor():
    """Diagnose system dependencies and configuration."""
    logger.info("Command: doctor")
    cfg = load_config()
    setup_logging(cfg.system.log_path)

    console.print("[bold]Prime Directive Doctor[/bold]")
    if cfg.system.mock_mode:
        console.print("[bold yellow]MOCK MODE ENABLED[/bold yellow]")

    checks = []

    # 1. Tmux
    if cfg.system.mock_mode:
        checks.append(("Tmux Installed", "✅", "Mocked"))
    else:
        tmux_path = shutil.which("tmux")
        checks.append(
            (
                "Tmux Installed",
                "✅" if tmux_path else "❌",
                tmux_path or "Not found",
            )
        )

    # 2. Editor
    if cfg.system.mock_mode:
        checks.append((f"Editor ({cfg.system.editor_cmd})", "✅", "Mocked"))
    else:
        editor_cmd = cfg.system.editor_cmd
        editor_path = shutil.which(editor_cmd)
        checks.append(
            (
                f"Editor ({editor_cmd})",
                "✅" if editor_path else "❌",
                editor_path or "Not found in PATH",
            )
        )

    # 3. AI Model (Ollama)
    if cfg.system.mock_mode:
        checks.append(("AI Engine (Ollama)", "✅", "Mocked"))
    else:
        ollama = get_ollama_status(cfg.system.ai_model)
        if not ollama.installed:
            ai_status = "❌"
            ai_msg = f"{ollama.details}. Install: {ollama.install_cmd}"
        elif not ollama.running:
            ai_status = "❌"
            ai_msg = f"{ollama.details}. Start: {ollama.start_cmd}"
        else:
            if "missing" in ollama.details.lower():
                ai_status = "⚠️"
            else:
                ai_status = "✅"
            ai_msg = ollama.details
        checks.append(("AI Engine (Ollama)", ai_status, ai_msg))

    # 3b. OpenAI fallback availability (optional)
    if cfg.system.mock_mode:
        checks.append(("OpenAI Fallback", "✅", "Mocked"))
    else:
        if has_openai_api_key():
            checks.append(("OpenAI Fallback", "✅", "OPENAI_API_KEY set"))
        else:
            checks.append(("OpenAI Fallback", "⚠️", "OPENAI_API_KEY not set"))

    # 3c. Check for multiple pd installations (can cause config shadowing)
    if cfg.system.mock_mode:
        checks.append(("Installation", "✅", "Mocked"))
    else:
        pd_locations = []
        search_paths = [
            Path.home() / ".local" / "bin" / "pd",
            Path.home()
            / ".local"
            / "share"
            / "uv"
            / "tools"
            / "prime-directive",
            Path.home()
            / ".local"
            / "share"
            / "pipx"
            / "venvs"
            / "prime-directive",
        ]
        for p in search_paths:
            if p.exists():
                pd_locations.append(str(p))
        if pd_locations:
            checks.append(
                (
                    "Installation",
                    "⚠️",
                    f"Multiple installs detected: {', '.join(pd_locations)}. "
                    "May cause config shadowing. Remove with: rm -rf <path>",
                )
            )
        else:
            checks.append(
                ("Installation", "✅", "Single installation (editable)")
            )

    # 5. Shell integration
    current_shell = os.environ.get("SHELL", "")
    if "zsh" in current_shell:
        checks.append(
            ("Shell Integration", "✅", f"zsh detected ({current_shell})")
        )
    elif current_shell:
        checks.append(
            (
                "Shell Integration",
                "⚠️",
                f"{current_shell} detected — shell_integration.zsh is ZSH-only. "
                "Source prime_directive/system/shell_integration.bash for Bash.",
            )
        )
    else:
        checks.append(
            (
                "Shell Integration",
                "⚠️",
                "$SHELL not set; cannot verify integration",
            )
        )

    # 4. Registry Paths
    console.print("\n[bold]Checking Repositories:[/bold]")
    for repo in cfg.repos.values():
        exists = os.path.exists(repo.path)
        icon = "✅" if exists else "❌"
        console.print(f"  {icon} {repo.id}: {repo.path}")
        if not exists:
            checks.append((f"Repo {repo.id}", "❌", "Path not found"))

    console.print("\n[bold]System Checks:[/bold]")
    table = Table(show_header=False)
    for name, icon, msg in checks:
        table.add_row(name, icon, msg)
    console.print(table)

    # Log results
    logger.info(f"Doctor checks: {checks}")
