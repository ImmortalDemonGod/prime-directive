from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

VALID_SKILL_DEPTHS = {"expert", "proficient", "familiar"}
VALID_SKILL_RECENCY = {"active", "recent", "historical"}
CONNECTION_SURFACE_FIELDS = (
    "experience_tags",
    "topic_tags",
    "geographic_tags",
    "education_tags",
    "industry_tags",
    "hobby_tags",
    "philosophy_tags",
)


@dataclass
class Education:
    institution: str = ""
    degree: str = ""
    field: str = ""
    years: str = ""
    notable: Optional[str] = None


@dataclass
class MilitaryService:
    branch: str = ""
    rate_mos: str = ""
    specialty: str = ""
    clearance: Optional[str] = None
    years: str = ""
    stations: list[str] = field(default_factory=list)
    deployments: list[str] = field(default_factory=list)


@dataclass
class GeographicEntry:
    location: str = ""
    years: str = ""


@dataclass
class Publication:
    title: str = ""
    venue: str = ""
    year: int = 0
    tags: list[str] = field(default_factory=list)


@dataclass
class HumanIdentity:
    education: list[Education] = field(default_factory=list)
    military: Optional[MilitaryService] = None
    geographic_history: list[GeographicEntry] = field(default_factory=list)
    languages: dict[str, list[str]] = field(
        default_factory=lambda: {"spoken": [], "programming": []}
    )
    hobbies: list[str] = field(default_factory=list)
    formative_experiences: list[str] = field(default_factory=list)
    intellectual_influences: list[str] = field(default_factory=list)
    publications: list[Publication] = field(default_factory=list)
    values: list[str] = field(default_factory=list)


@dataclass
class Skill:
    name: str = ""
    depth: str = ""
    recency: str = ""
    evidence: str = ""


@dataclass
class ProjectBuilt:
    name: str = ""
    description: str = ""
    tech_stack: list[str] = field(default_factory=list)
    capability_tags: list[str] = field(default_factory=list)
    url: Optional[str] = None


@dataclass
class Methodology:
    name: str = ""
    description: str = ""
    applicable_contexts: list[str] = field(default_factory=list)
    evidence: str = ""


@dataclass
class TechnicalCapabilities:
    skills: list[Skill] = field(default_factory=list)
    domain_expertise: list[str] = field(default_factory=list)
    research: list[dict[str, Any]] = field(default_factory=list)
    projects_built: list[ProjectBuilt] = field(default_factory=list)
    methodologies: list[Methodology] = field(default_factory=list)
    audit_portfolio: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Company:
    name: str = ""
    role: str = ""
    years: str = ""
    accomplishment: str = ""


@dataclass
class ProfessionalNetwork:
    companies: list[Company] = field(default_factory=list)
    industries: list[str] = field(default_factory=list)
    testimonials: list[dict[str, Any]] = field(default_factory=list)
    communities: list[dict[str, Any]] = field(default_factory=list)
    collaborators: list[dict[str, Any]] = field(default_factory=list)
    institutional_overlaps: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Offering:
    name: str = ""
    description: str = ""
    deliverable: str = ""
    typical_timeline: str = ""


@dataclass
class StrategicPositioning:
    positioning_statement: str = ""
    competitive_differentiation: list[str] = field(default_factory=list)
    offerings: list[Offering] = field(default_factory=list)
    active_engagements: list[dict[str, Any]] = field(default_factory=list)
    case_studies: list[dict[str, Any]] = field(default_factory=list)
    revenue_model: str = ""


@dataclass
class ConnectionSurface:
    experience_tags: list[str] = field(default_factory=list)
    topic_tags: list[str] = field(default_factory=list)
    geographic_tags: list[str] = field(default_factory=list)
    education_tags: list[str] = field(default_factory=list)
    industry_tags: list[str] = field(default_factory=list)
    hobby_tags: list[str] = field(default_factory=list)
    philosophy_tags: list[str] = field(default_factory=list)


@dataclass
class OperatorDossier:
    version: str = "3.1"
    identity: HumanIdentity = field(default_factory=HumanIdentity)
    capabilities: TechnicalCapabilities = field(default_factory=TechnicalCapabilities)
    network: ProfessionalNetwork = field(default_factory=ProfessionalNetwork)
    positioning: StrategicPositioning = field(default_factory=StrategicPositioning)
    connection_surface: ConnectionSurface = field(default_factory=ConnectionSurface)


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors


def get_dossier_path() -> Path:
    return Path.home() / ".prime-directive" / "operator_dossier.yaml"


def default_operator_dossier() -> OperatorDossier:
    return OperatorDossier()


def operator_dossier_to_dict(dossier: OperatorDossier) -> dict[str, Any]:
    return asdict(dossier)


def sync_connection_surface(dossier: OperatorDossier) -> OperatorDossier:
    preserved_philosophy_tags = [
        normalize_tag(tag)
        for tag in dossier.connection_surface.philosophy_tags
        if str(tag).strip()
    ]

    experience_tags: set[str] = set()
    if dossier.identity.military is not None:
        experience_tags.add("military")
    if dossier.identity.education or dossier.identity.publications:
        experience_tags.add("research")
    for entry in dossier.identity.formative_experiences:
        lowered = entry.lower()
        if "pivot" in lowered or "transition" in lowered:
            experience_tags.add("career-pivot")
        if "self-taught" in lowered or "no formal" in lowered:
            experience_tags.add("self-taught")
        if "open-source" in lowered or "open source" in lowered:
            experience_tags.add("open-source")

    topic_tags = _normalized_tag_set(dossier.capabilities.domain_expertise)
    for publication in dossier.identity.publications:
        topic_tags.update(_normalized_tag_set(publication.tags))
    for project in dossier.capabilities.projects_built:
        topic_tags.update(_normalized_tag_set(project.capability_tags))
    for research_item in dossier.capabilities.research:
        topic_tags.update(_normalized_tag_set(_as_list(research_item.get("tags"))))

    geographic_tags = {
        normalize_tag(entry.location.replace(",", " "))
        for entry in dossier.identity.geographic_history
        if entry.location.strip()
    }
    education_tags = set()
    for education in dossier.identity.education:
        if education.institution.strip():
            education_tags.add(normalize_tag(education.institution))
        if education.field.strip():
            education_tags.add(normalize_tag(education.field))
    industry_tags = _normalized_tag_set(dossier.network.industries)
    hobby_tags = _normalized_tag_set(dossier.identity.hobbies)

    dossier.connection_surface = ConnectionSurface(
        experience_tags=sorted(experience_tags),
        topic_tags=sorted(topic_tags),
        geographic_tags=sorted(geographic_tags),
        education_tags=sorted(education_tags),
        industry_tags=sorted(industry_tags),
        hobby_tags=sorted(hobby_tags),
        philosophy_tags=sorted(set(preserved_philosophy_tags)),
    )
    return dossier


def write_operator_dossier(
    dossier: OperatorDossier,
    path: Optional[Path] = None,
) -> Path:
    target_path = path or get_dossier_path()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(
            operator_dossier_to_dict(dossier),
            handle,
            sort_keys=False,
            allow_unicode=True,
        )
    return target_path


def load_operator_dossier(path: Optional[Path] = None) -> OperatorDossier:
    target_path = path or get_dossier_path()
    report, raw_data = validate_operator_dossier_file(target_path)
    if report.errors:
        formatted_errors = "\n".join(f"- {item}" for item in report.errors)
        raise ValueError(
            f"Operator dossier validation failed for {target_path}:\n{formatted_errors}"
        )
    return parse_operator_dossier(raw_data)


def validate_operator_dossier_file(
    path: Optional[Path] = None,
) -> tuple[ValidationReport, dict[str, Any]]:
    target_path = path or get_dossier_path()
    report = ValidationReport()
    if not target_path.exists():
        report.errors.append(f"Dossier file not found: {target_path}")
        return report, {}
    try:
        with target_path.open("r", encoding="utf-8") as handle:
            raw_data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        report.errors.append(f"Invalid YAML: {exc}")
        return report, {}
    if not isinstance(raw_data, dict):
        report.errors.append("Top-level dossier content must be a mapping.")
        return report, {}
    validate_operator_dossier_data(raw_data, report)
    return report, raw_data


def validate_operator_dossier_data(
    raw_data: dict[str, Any],
    report: Optional[ValidationReport] = None,
) -> ValidationReport:
    current = report or ValidationReport()
    version = raw_data.get("version")
    if version != "3.1":
        current.errors.append(
            f'Invalid dossier version: expected "3.1", got {version!r}'
        )

    capabilities = _as_dict(raw_data.get("capabilities"))
    for index, skill in enumerate(_as_list(capabilities.get("skills"))):
        skill_dict = _as_dict(skill)
        depth = str(skill_dict.get("depth", "")).strip()
        recency = str(skill_dict.get("recency", "")).strip()
        if depth not in VALID_SKILL_DEPTHS:
            current.errors.append(
                f"capabilities.skills[{index}].depth must be one of "
                f"{sorted(VALID_SKILL_DEPTHS)}"
            )
        if recency not in VALID_SKILL_RECENCY:
            current.errors.append(
                f"capabilities.skills[{index}].recency must be one of "
                f"{sorted(VALID_SKILL_RECENCY)}"
            )

    for location, tags in _iter_normalized_tag_lists(raw_data):
        _validate_tag_list(location, tags, current)

    connection_surface = _as_dict(raw_data.get("connection_surface"))
    for field_name in CONNECTION_SURFACE_FIELDS:
        field_tags = _as_list(connection_surface.get(field_name))
        if len(field_tags) > 50:
            current.warnings.append(
                f"connection_surface.{field_name} has more than 50 tags"
            )

    skill_names = {
        str(skill.get("name", "")).strip().lower()
        for skill in _as_list(capabilities.get("skills"))
        if isinstance(skill, dict) and str(skill.get("name", "")).strip()
    }
    for project in _as_list(capabilities.get("projects_built")):
        project_dict = _as_dict(project)
        project_name = str(project_dict.get("name", "project")).strip() or "project"
        for tech in _as_list(project_dict.get("tech_stack")):
            normalized = str(tech).strip().lower()
            if normalized and normalized not in skill_names:
                current.warnings.append(
                    f'projects_built.{project_name}.tech_stack entry "{tech}" '
                    "has no matching skill entry"
                )

    for layer_name in ("identity", "capabilities", "network", "positioning"):
        if _is_empty_layer(raw_data.get(layer_name)):
            current.info.append(f"{layer_name} is empty")

    philosophy_tags = _as_list(connection_surface.get("philosophy_tags"))
    if philosophy_tags:
        current.info.append(
            f"connection_surface.philosophy_tags: {len(philosophy_tags)} tags present"
        )
    else:
        current.info.append("connection_surface.philosophy_tags is empty")

    return current


def parse_operator_dossier(raw_data: dict[str, Any]) -> OperatorDossier:
    identity = _as_dict(raw_data.get("identity"))
    capabilities = _as_dict(raw_data.get("capabilities"))
    network = _as_dict(raw_data.get("network"))
    positioning = _as_dict(raw_data.get("positioning"))
    connection_surface = _as_dict(raw_data.get("connection_surface"))

    military_raw = _as_dict(identity.get("military"))
    military = None
    if military_raw:
        military = MilitaryService(
            branch=str(military_raw.get("branch", "")),
            rate_mos=str(military_raw.get("rate_mos", "")),
            specialty=str(military_raw.get("specialty", "")),
            clearance=_optional_str(military_raw.get("clearance")),
            years=str(military_raw.get("years", "")),
            stations=[str(item) for item in _as_list(military_raw.get("stations"))],
            deployments=[
                str(item) for item in _as_list(military_raw.get("deployments"))
            ],
        )

    return OperatorDossier(
        version=str(raw_data.get("version", "")),
        identity=HumanIdentity(
            education=[
                Education(
                    institution=str(item.get("institution", "")),
                    degree=str(item.get("degree", "")),
                    field=str(item.get("field", "")),
                    years=str(item.get("years", "")),
                    notable=_optional_str(item.get("notable")),
                )
                for item in (_as_dict(entry) for entry in _as_list(identity.get("education")))
            ],
            military=military,
            geographic_history=[
                GeographicEntry(
                    location=str(item.get("location", "")),
                    years=str(item.get("years", "")),
                )
                for item in (
                    _as_dict(entry)
                    for entry in _as_list(identity.get("geographic_history"))
                )
            ],
            languages={
                "spoken": [
                    str(item)
                    for item in _as_list(_as_dict(identity.get("languages")).get("spoken"))
                ],
                "programming": [
                    str(item)
                    for item in _as_list(
                        _as_dict(identity.get("languages")).get("programming")
                    )
                ],
            },
            hobbies=[str(item) for item in _as_list(identity.get("hobbies"))],
            formative_experiences=[
                str(item)
                for item in _as_list(identity.get("formative_experiences"))
            ],
            intellectual_influences=[
                str(item)
                for item in _as_list(identity.get("intellectual_influences"))
            ],
            publications=[
                Publication(
                    title=str(item.get("title", "")),
                    venue=str(item.get("venue", "")),
                    year=int(item.get("year", 0) or 0),
                    tags=[str(tag) for tag in _as_list(item.get("tags"))],
                )
                for item in (
                    _as_dict(entry) for entry in _as_list(identity.get("publications"))
                )
            ],
            values=[str(item) for item in _as_list(identity.get("values"))],
        ),
        capabilities=TechnicalCapabilities(
            skills=[
                Skill(
                    name=str(item.get("name", "")),
                    depth=str(item.get("depth", "")),
                    recency=str(item.get("recency", "")),
                    evidence=str(item.get("evidence", "")),
                )
                for item in (_as_dict(entry) for entry in _as_list(capabilities.get("skills")))
            ],
            domain_expertise=[
                str(item) for item in _as_list(capabilities.get("domain_expertise"))
            ],
            research=[
                _as_dict(item) for item in _as_list(capabilities.get("research"))
            ],
            projects_built=[
                ProjectBuilt(
                    name=str(item.get("name", "")),
                    description=str(item.get("description", "")),
                    tech_stack=[str(tag) for tag in _as_list(item.get("tech_stack"))],
                    capability_tags=[
                        str(tag) for tag in _as_list(item.get("capability_tags"))
                    ],
                    url=_optional_str(item.get("url")),
                )
                for item in (
                    _as_dict(entry)
                    for entry in _as_list(capabilities.get("projects_built"))
                )
            ],
            methodologies=[
                Methodology(
                    name=str(item.get("name", "")),
                    description=str(item.get("description", "")),
                    applicable_contexts=[
                        str(tag)
                        for tag in _as_list(item.get("applicable_contexts"))
                    ],
                    evidence=str(item.get("evidence", "")),
                )
                for item in (
                    _as_dict(entry)
                    for entry in _as_list(capabilities.get("methodologies"))
                )
            ],
            audit_portfolio=[
                _as_dict(item)
                for item in _as_list(capabilities.get("audit_portfolio"))
            ],
        ),
        network=ProfessionalNetwork(
            companies=[
                Company(
                    name=str(item.get("name", "")),
                    role=str(item.get("role", "")),
                    years=str(item.get("years", "")),
                    accomplishment=str(item.get("accomplishment", "")),
                )
                for item in (_as_dict(entry) for entry in _as_list(network.get("companies")))
            ],
            industries=[str(item) for item in _as_list(network.get("industries"))],
            testimonials=[
                _as_dict(item) for item in _as_list(network.get("testimonials"))
            ],
            communities=[_as_dict(item) for item in _as_list(network.get("communities"))],
            collaborators=[
                _as_dict(item) for item in _as_list(network.get("collaborators"))
            ],
            institutional_overlaps=[
                _as_dict(item)
                for item in _as_list(network.get("institutional_overlaps"))
            ],
        ),
        positioning=StrategicPositioning(
            positioning_statement=str(positioning.get("positioning_statement", "")),
            competitive_differentiation=[
                str(item)
                for item in _as_list(
                    positioning.get("competitive_differentiation")
                )
            ],
            offerings=[
                Offering(
                    name=str(item.get("name", "")),
                    description=str(item.get("description", "")),
                    deliverable=str(item.get("deliverable", "")),
                    typical_timeline=str(item.get("typical_timeline", "")),
                )
                for item in (
                    _as_dict(entry) for entry in _as_list(positioning.get("offerings"))
                )
            ],
            active_engagements=[
                _as_dict(item)
                for item in _as_list(positioning.get("active_engagements"))
            ],
            case_studies=[
                _as_dict(item) for item in _as_list(positioning.get("case_studies"))
            ],
            revenue_model=str(positioning.get("revenue_model", "")),
        ),
        connection_surface=ConnectionSurface(
            experience_tags=sorted(
                [
                    str(item)
                    for item in _as_list(connection_surface.get("experience_tags"))
                ]
            ),
            topic_tags=sorted(
                [str(item) for item in _as_list(connection_surface.get("topic_tags"))]
            ),
            geographic_tags=sorted(
                [
                    str(item)
                    for item in _as_list(connection_surface.get("geographic_tags"))
                ]
            ),
            education_tags=sorted(
                [
                    str(item)
                    for item in _as_list(connection_surface.get("education_tags"))
                ]
            ),
            industry_tags=sorted(
                [str(item) for item in _as_list(connection_surface.get("industry_tags"))]
            ),
            hobby_tags=sorted(
                [str(item) for item in _as_list(connection_surface.get("hobby_tags"))]
            ),
            philosophy_tags=sorted(
                [
                    str(item)
                    for item in _as_list(connection_surface.get("philosophy_tags"))
                ]
            ),
        ),
    )


def _iter_normalized_tag_lists(
    raw_data: dict[str, Any],
) -> list[tuple[str, list[str]]]:
    capabilities = _as_dict(raw_data.get("capabilities"))
    identity = _as_dict(raw_data.get("identity"))
    connection_surface = _as_dict(raw_data.get("connection_surface"))

    collected: list[tuple[str, list[str]]] = [
        (
            "capabilities.domain_expertise",
            [str(item) for item in _as_list(capabilities.get("domain_expertise"))],
        )
    ]
    for index, item in enumerate(_as_list(identity.get("publications"))):
        publication = _as_dict(item)
        collected.append(
            (
                f"identity.publications[{index}].tags",
                [str(tag) for tag in _as_list(publication.get("tags"))],
            )
        )
    for index, item in enumerate(_as_list(capabilities.get("projects_built"))):
        project = _as_dict(item)
        collected.append(
            (
                f"capabilities.projects_built[{index}].capability_tags",
                [str(tag) for tag in _as_list(project.get("capability_tags"))],
            )
        )
    for field_name in CONNECTION_SURFACE_FIELDS:
        collected.append(
            (
                f"connection_surface.{field_name}",
                [str(tag) for tag in _as_list(connection_surface.get(field_name))],
            )
        )
    return collected


def _validate_tag_list(
    location: str,
    tags: list[str],
    report: ValidationReport,
) -> None:
    seen: set[str] = set()
    duplicate_tags: set[str] = set()
    for tag in tags:
        normalized = normalize_tag(tag)
        if tag != normalized:
            report.warnings.append(
                f'{location} contains non-normalized tag "{tag}"; '
                f'suggested "{normalized}"'
            )
        if tag in seen:
            duplicate_tags.add(tag)
        seen.add(tag)
    for tag in sorted(duplicate_tags):
        report.warnings.append(f'{location} contains duplicate tag "{tag}"')


def preview_operator_dossier_tag_normalization_fixes(
    raw_data: dict[str, Any],
) -> list[str]:
    fixes: list[str] = []
    for location, tags in _iter_normalized_tag_lists(raw_data):
        for tag in tags:
            normalized = normalize_tag(tag)
            if tag != normalized:
                fixes.append(f'{location}: "{tag}" -> "{normalized}"')
    return fixes


def apply_operator_dossier_tag_normalization_fixes(
    raw_data: dict[str, Any],
) -> list[str]:
    fixes: list[str] = []
    capabilities = raw_data.get("capabilities")
    identity = raw_data.get("identity")
    connection_surface = raw_data.get("connection_surface")

    if isinstance(capabilities, dict) and isinstance(
        capabilities.get("domain_expertise"),
        list,
    ):
        capabilities["domain_expertise"], field_fixes = _normalize_tag_sequence(
            [str(item) for item in capabilities["domain_expertise"]],
            "capabilities.domain_expertise",
        )
        fixes.extend(field_fixes)

    if isinstance(identity, dict):
        publications = identity.get("publications")
        if isinstance(publications, list):
            for index, item in enumerate(publications):
                if not isinstance(item, dict) or not isinstance(item.get("tags"), list):
                    continue
                item["tags"], field_fixes = _normalize_tag_sequence(
                    [str(tag) for tag in item["tags"]],
                    f"identity.publications[{index}].tags",
                )
                fixes.extend(field_fixes)

    if isinstance(capabilities, dict):
        projects_built = capabilities.get("projects_built")
        if isinstance(projects_built, list):
            for index, item in enumerate(projects_built):
                if not isinstance(item, dict) or not isinstance(
                    item.get("capability_tags"),
                    list,
                ):
                    continue
                item["capability_tags"], field_fixes = _normalize_tag_sequence(
                    [str(tag) for tag in item["capability_tags"]],
                    f"capabilities.projects_built[{index}].capability_tags",
                )
                fixes.extend(field_fixes)

    if isinstance(connection_surface, dict):
        for field_name in CONNECTION_SURFACE_FIELDS:
            tags = connection_surface.get(field_name)
            if not isinstance(tags, list):
                continue
            connection_surface[field_name], field_fixes = _normalize_tag_sequence(
                [str(tag) for tag in tags],
                f"connection_surface.{field_name}",
            )
            fixes.extend(field_fixes)

    return fixes


def normalize_tag(value: str) -> str:
    normalized = value.strip().lower().replace("_", "-")
    normalized = "-".join(part for part in normalized.replace("/", " ").split())
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    return normalized


def _normalize_tag_sequence(
    tags: list[str],
    location: str,
) -> tuple[list[str], list[str]]:
    normalized_tags: list[str] = []
    fixes: list[str] = []
    for tag in tags:
        normalized = normalize_tag(tag)
        normalized_tags.append(normalized)
        if tag != normalized:
            fixes.append(f'{location}: "{tag}" -> "{normalized}"')
    return normalized_tags, fixes


def _normalized_tag_set(values: list[Any]) -> set[str]:
    return {
        normalize_tag(str(value))
        for value in values
        if str(value).strip()
    }


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _is_empty_layer(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, dict):
        for item in value.values():
            if not _is_empty_layer(item):
                return False
        return True
    if isinstance(value, list):
        return all(_is_empty_layer(item) for item in value)
    if isinstance(value, str):
        return not value.strip()
    return False
