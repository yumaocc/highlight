from pydantic import BaseModel, Field
from typing import Optional


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    description: str = ""
    status: str = Field("active", max_length=40)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    description: Optional[str] = None
    status: Optional[str] = Field(default=None, max_length=40)


class PipelineRunCreate(BaseModel):
    template_key: str = Field(..., min_length=1, max_length=120)
    source_video_id: Optional[int] = None
    source_video_ids: list[int] = Field(default_factory=list)
    params: dict = Field(default_factory=dict)
    prompt_config_ids: list[int] = Field(default_factory=list)

    def resolved_source_video_ids(self) -> list[int]:
        ids = list(self.source_video_ids)
        if self.source_video_id is not None and self.source_video_id not in ids:
            ids.insert(0, self.source_video_id)
        return ids


class ResourceImportCreate(BaseModel):
    project_id: int
    baidu_url: str = Field(..., min_length=1)
    extract_code: str = ""
    drama_name: str = ""
    episode_limit: int = Field(5, ge=1, le=50)
    recursive: bool = True
    max_depth: int = Field(4, ge=0, le=8)
    pipeline_template_key: str = Field("story_quality_cut", min_length=1, max_length=120)
    enqueue_pipeline: bool = True


class QingqueResourceMatch(BaseModel):
    drama_name: str
    baidu_url: str
    extract_code: str = ""
    raw_link_text: str = ""
    sheet_id: str
    sheet_name: str
    row: int
    score: float
    match_type: str


DEFAULT_AUTO_PUBLISH_TOPICS = ["快来看短剧", "AI创想家计划", "神仙剪刀手"]


class AutoPublishCreate(BaseModel):
    drama_names: list[str] = Field(..., min_length=1, max_length=50)
    episode_limit: int = Field(5, ge=1, le=50)
    pipeline_template_key: str = Field("episode_concat_visual", min_length=1, max_length=120)
    publish_enabled: bool = True
    publish_base_url: str = "http://127.0.0.1:5409"
    platform: str = "kuaishou"
    account_ids: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=lambda: DEFAULT_AUTO_PUBLISH_TOPICS.copy())
    is_original: bool = True
    schedule_at: str = ""
    kuaishou_enable_promotion_task: bool = True
    skip_existing: bool = True
    max_concurrency: int = Field(2, ge=1, le=4)


class ClipCreate(BaseModel):
    start: str = Field(..., examples=["00:00:12.5"])
    end: str = Field(..., examples=["00:00:42"])
    reason: str = ""


class ScanResult(BaseModel):
    indexed: int
    failed: list[str]


class PromptConfigCreate(BaseModel):
    key: str = Field(..., min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    name: str = Field(..., min_length=1, max_length=120)
    category: str = Field("video_generation", min_length=1, max_length=80)
    description: str = ""
    content: str = Field(..., min_length=1)
    enabled: bool = True


class PromptConfigUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    category: Optional[str] = Field(default=None, min_length=1, max_length=80)
    description: Optional[str] = None
    content: Optional[str] = Field(default=None, min_length=1)
    enabled: Optional[bool] = None


class IntroTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    drama_name: str = Field("", max_length=160)
    style: str = Field("", max_length=80)
    summary: str = ""
    duration: int = Field(2, ge=1, le=30)
    asset_path: str = ""
    image_path: str = ""
    image_url: str = ""
    intro_image_path: str = ""
    intro_image_url: str = ""
    outro_image_path: str = ""
    outro_image_url: str = ""
    prompt: str = ""
    source: str = Field("manual", pattern=r"^(manual|ai)$")
    status: str = Field("draft", pattern=r"^(draft|ready)$")


class IntroTemplateUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=160)
    drama_name: Optional[str] = Field(default=None, max_length=160)
    style: Optional[str] = Field(default=None, max_length=80)
    summary: Optional[str] = None
    duration: Optional[int] = Field(default=None, ge=1, le=30)
    asset_path: Optional[str] = None
    image_path: Optional[str] = None
    image_url: Optional[str] = None
    intro_image_path: Optional[str] = None
    intro_image_url: Optional[str] = None
    outro_image_path: Optional[str] = None
    outro_image_url: Optional[str] = None
    prompt: Optional[str] = None
    source: Optional[str] = Field(default=None, pattern=r"^(manual|ai)$")
    status: Optional[str] = Field(default=None, pattern=r"^(draft|ready)$")


class IntroTemplateVisualGenerate(BaseModel):
    kind: str = Field(..., pattern=r"^(intro|outro)$")
    drama_name: str = Field(..., min_length=1, max_length=160)
    style: str = Field("强冲突快节奏", max_length=80)
    brief: str = ""
    duration: int = Field(2, ge=1, le=30)
    reference_image_path: str = ""
    template_id: Optional[int] = None


class IntroWorkflowRunCreate(BaseModel):
    template_id: int
    source_video_ids: list[int] = Field(default_factory=list)
