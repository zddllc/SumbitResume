"""Common resume fields and validated application input."""

from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from utils.llm_client import Provider


Text = Annotated[str, Field(max_length=10000)]
ShortText = Annotated[str, Field(max_length=500)]
Answer = Literal["unspecified", "yes", "no", "decline"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LoginInput(Model):
    email: Annotated[str, Field(min_length=1, max_length=254)]
    password: Annotated[
        str, StringConstraints(strip_whitespace=False),
        Field(min_length=1, max_length=1024, repr=False),
    ]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class SetupInput(LoginInput):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    password: Annotated[
        str, StringConstraints(strip_whitespace=False),
        Field(min_length=8, max_length=1024, repr=False),
    ]


class Contact(Model):
    name: ShortText = ""
    email: ShortText = ""
    phone: ShortText = ""
    location: ShortText = ""
    linkedin: ShortText = ""
    website: ShortText = ""


class Experience(Model):
    company: ShortText = ""
    title: ShortText = ""
    location: ShortText = ""
    start_date: ShortText = ""
    end_date: ShortText = ""
    bullets: list[Text] = Field(default_factory=list, max_length=50)


class Education(Model):
    institution: ShortText = ""
    degree: ShortText = ""
    field: ShortText = ""
    start_date: ShortText = ""
    end_date: ShortText = ""
    details: list[Text] = Field(default_factory=list, max_length=20)


class Project(Model):
    name: ShortText = ""
    url: ShortText = ""
    bullets: list[Text] = Field(default_factory=list, max_length=50)


class Certification(Model):
    name: ShortText = ""
    issuer: ShortText = ""
    date: ShortText = ""


class Language(Model):
    name: ShortText = ""
    proficiency: ShortText = ""


class Publication(Model):
    title: ShortText = ""
    authors: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(default_factory=list, max_length=100)
    venue: ShortText = ""
    date: ShortText = ""
    doi: ShortText = ""
    url: ShortText = ""
    details: list[Annotated[str, Field(min_length=1, max_length=10000)]] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_content(self) -> "Publication":
        if not any((self.title, self.authors, self.venue, self.date, self.doi, self.url, self.details)):
            raise ValueError("论文条目不能为空，请填写内容或删除该条")
        return self


class ResumeProfile(Model):
    contact: Contact = Field(default_factory=Contact)
    summary: Text = ""
    skills: list[ShortText] = Field(default_factory=list, max_length=150)
    experience: list[Experience] = Field(default_factory=list, max_length=50)
    education: list[Education] = Field(default_factory=list, max_length=30)
    publications: list[Publication] = Field(default_factory=list, max_length=100)
    projects: list[Project] = Field(default_factory=list, max_length=50)
    certifications: list[Certification] = Field(default_factory=list, max_length=50)
    languages: list[Language] = Field(default_factory=list, max_length=30)


def resume_cache_data(profile: ResumeProfile) -> dict:
    data = profile.model_dump()
    # Empty optional sections must not invalidate pre-publication resume caches.
    if not profile.publications:
        data.pop("publications")
    return data


class PersonalInfo(Model):
    work_authorization: ShortText = ""
    needs_sponsorship: Answer = "unspecified"
    willing_to_relocate: Answer = "unspecified"
    preferred_locations: list[ShortText] = Field(default_factory=list, max_length=30)
    notice_period: ShortText = ""
    salary_expectation: ShortText = ""
    veteran_status: Literal[
        "unspecified", "not_veteran", "veteran", "decline"
    ] = "unspecified"
    disability_status: Answer = "unspecified"


class LLMSettings(Model):
    provider: Provider = "deepseek"
    model: ShortText = "deepseek-flash"
    base_url: ShortText = ""
    api_version: ShortText = "2024-12-01-preview"
    api_key: Annotated[str, Field(max_length=4096, repr=False)] = ""

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        if value:
            parts = urlsplit(value)
            local_http = parts.scheme == "http" and parts.hostname in {
                "localhost", "127.0.0.1"
            }
            if (parts.scheme != "https" and not local_http) or not parts.hostname:
                raise ValueError("API 地址必须使用 HTTPS，本机调试可用 HTTP")
            if parts.username or parts.password or parts.query or parts.fragment:
                raise ValueError("API 地址不能包含账密、查询参数或片段")
        return value.rstrip("/")


class CredentialInput(Model):
    site: ShortText
    label: ShortText = ""
    username: Annotated[str, Field(min_length=1, max_length=500, repr=False)]
    password: Annotated[
        str, StringConstraints(strip_whitespace=False),
        Field(min_length=1, max_length=4096, repr=False),
    ]

    @field_validator("site")
    @classmethod
    def validate_site(cls, value: str) -> str:
        parts = urlsplit(value if "://" in value else "https://" + value)
        if (
            parts.scheme != "https" or not parts.hostname
            or parts.username or parts.password
            or parts.port not in (None, 443)
            or parts.hostname in {"localhost", "127.0.0.1"}
        ):
            raise ValueError("外站请填写有效的 HTTPS 域名，不要在地址中填写账密")
        return "https://" + parts.hostname.lower()


class JobPost(Model):
    linkedin_id: Annotated[str, Field(pattern=r"^\d{1,30}$")]
    url: ShortText
    title: Annotated[str, Field(min_length=1, max_length=500)]
    company: ShortText = ""
    location: ShortText = ""
    description: Annotated[str, Field(min_length=20, max_length=100000)]
    application_kind: Literal["external", "easy_apply", "unavailable"] = "unavailable"
    application_url: Annotated[str, Field(max_length=8000)] | None = None
    application_landing_url: Annotated[str, Field(max_length=8000)] | None = None
    application_url_source: Literal["company_apply_link", "external_redirect"] | None = None
    application_error: ShortText | None = None

    @field_validator("application_url", "application_landing_url")
    @classmethod
    def validate_application_url(cls, value: str | None) -> str | None:
        if value is not None:
            parts = urlsplit(value)
            if (
                parts.scheme != "https" or not parts.hostname
                or parts.username or parts.password
                or parts.hostname in {"localhost", "127.0.0.1", "::1"}
                or parts.hostname.endswith(".localhost")
            ):
                raise ValueError("申请链接必须是有效的外站 HTTPS 地址")
            if parts.hostname == "linkedin.com" or parts.hostname.endswith(".linkedin.com"):
                raise ValueError("外站申请链接不能指向 LinkedIn")
        return value

    @model_validator(mode="after")
    def validate_application_kind(self) -> "JobPost":
        if self.application_kind == "external" and not self.application_url:
            raise ValueError("外站申请需要有效的申请链接")
        if self.application_kind != "external" and (
            self.application_url or self.application_landing_url or self.application_url_source
        ):
            raise ValueError("非外站申请不能包含外站申请链接")
        return self


class BulletRewrite(Model):
    source_index: Annotated[int, Field(ge=0, strict=True)]
    text: Annotated[str, Field(min_length=1, max_length=10000)]


class EntryRewrite(Model):
    source_index: Annotated[int, Field(ge=0, strict=True)]
    bullets: list[BulletRewrite] = Field(max_length=50)


class TailoringPlan(Model):
    summary: Text
    skills: list[ShortText] = Field(max_length=150)
    experience: list[EntryRewrite] = Field(max_length=50)
    projects: list[EntryRewrite] = Field(max_length=50)
